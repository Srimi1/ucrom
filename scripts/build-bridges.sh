#!/bin/bash
# Build the Halium bridge packages (packages/bridges.list) as arm64 .debs for
# Ubuntu noble, in dependency order, inside an arm64 build chroot.
#
#   scripts/build-bridges.sh              build everything not built yet
#   scripts/build-bridges.sh libhybris    (re)build one package
#
# Output: out/bridges/*.deb, out/bridges/status.tsv (name, result, version, note)
. "$(dirname "$0")/lib.sh"
need_root
ensure_arm64_exec

CHROOT="$BUILD_DIR/bridge-chroot"
DEST="$OUT_DIR/bridges"
STATUS="$DEST/status.tsv"
LIST="$UCROM_ROOT/packages/bridges.list"
ONLY="${1:-}"
mkdir -p "$DEST"
touch "$STATUS"

cleanup() {
    umount -l "$CHROOT/srv/bridges" 2>/dev/null || true
    chroot_umount "$CHROOT"
}
trap cleanup EXIT

if [ ! -x "$CHROOT/usr/bin/dpkg-buildpackage" ]; then
    log "creating arm64 build chroot"
    rm -rf "$CHROOT"
    retry 3 mmdebstrap --mode=root --variant=buildd --arch=arm64 \
        --components="main universe" \
        --include=devscripts,equivs,git,ca-certificates,fakeroot,dpkg-dev,quilt,lsb-release \
        --aptopt='APT::Install-Recommends "false"' \
        "$UCROM_SUITE" "$CHROOT" \
        "deb $UCROM_MIRROR $UCROM_SUITE main universe" \
        "deb $UCROM_MIRROR $UCROM_SUITE-updates main universe"
fi

chroot_mount "$CHROOT"
build_ca_install "$CHROOT"
mkdir -p "$CHROOT/srv/bridges" "$CHROOT/build"
mount --bind "$DEST" "$CHROOT/srv/bridges"
echo 'deb [trusted=yes] file:/srv/bridges ./' > "$CHROOT/etc/apt/sources.list.d/ucrom-bridges.list"

refresh_repo() {
    chroot_run "$CHROOT" sh -c 'cd /srv/bridges && dpkg-scanpackages -m . /dev/null > Packages 2>/dev/null'
    chroot_run "$CHROOT" apt-get update -qq -o Dir::Etc::sourceparts=- \
        -o Dir::Etc::sourcelist=sources.list.d/ucrom-bridges.list >/dev/null 2>&1 || true
    chroot_run "$CHROOT" apt-get update -qq >/dev/null 2>&1 || true
}

set_status() {  # name result version note
    grep -v "^$1	" "$STATUS" > "$STATUS.tmp" || true
    printf '%s\t%s\t%s\t%s\n' "$@" >> "$STATUS.tmp"
    mv "$STATUS.tmp" "$STATUS"
}

build_one() {
    local name=$1 repo=$2 branch=$3
    local src="/build/$name" log="$DEST/logs/$name.log"
    mkdir -p "$DEST/logs"
    log "bridge: $name ($repo @ $branch)"
    rm -rf "$CHROOT$src"
    if ! retry 3 git clone -q --depth 1 --recurse-submodules --shallow-submodules -b "$branch" "$repo" "$CHROOT$src" >"$log" 2>&1; then
        set_status "$name" FAIL - "clone failed"; return 1
    fi
    local commit; commit=$(git -C "$CHROOT$src" rev-parse --short HEAD)
    [ -d "$CHROOT$src/debian" ] || { set_status "$name" FAIL - "no debian/ packaging"; return 1; }
    # ucrom patches (Ubuntu noble build fixes), applied in order
    local p
    for p in "$UCROM_ROOT"/packages/patches/"$name"/*.patch; do
        [ -e "$p" ] || continue
        git -C "$CHROOT$src" apply "$p" >>"$log" 2>&1 || { set_status "$name" FAIL - "patch $(basename "$p") failed"; return 1; }
    done
    # Old Mer/Sailfish-style packaging asks for debhelper compat < 7, which
    # current debhelper refuses. Raise it to 10 (a packaging-only change).
    local compat="$CHROOT$src/debian/compat"
    if [ -f "$compat" ] && [ "$(tr -dc 0-9 < "$compat")" -lt 10 ]; then
        echo 10 > "$compat"
        echo "ucrom: debian/compat raised to 10" >>"$log"
    fi
    # Build-deps (from Ubuntu and from already-built bridges)
    if ! chroot_run "$CHROOT" sh -c "cd $src && mk-build-deps -i -r -t 'apt-get -y --no-install-recommends -o Debug::pkgProblemResolver=yes' debian/control" >>"$log" 2>&1; then
        local why; why=$(grep -E "Depends:|but it is not|Unable to locate|unmet" "$log" | tail -3 | tr '\n' ' ' | cut -c1-200)
        set_status "$name" FAIL "$commit" "build-deps: $why"; return 1
    fi
    if ! chroot_run "$CHROOT" sh -c "cd $src && DEB_BUILD_OPTIONS='nocheck parallel=$(nproc)' dpkg-buildpackage -us -uc -b -d" >>"$log" 2>&1 &&
       ! { echo "ucrom: parallel build failed, retrying with one job (make ordering races)" >>"$log";
           chroot_run "$CHROOT" sh -c "cd $src && git clean -fdxq -e debian && git checkout -q -- . && \
               { [ ! -f debian/compat ] || [ \$(tr -dc 0-9 < debian/compat) -ge 10 ] || echo 10 > debian/compat; } && \
               DEB_BUILD_OPTIONS='nocheck parallel=1' dpkg-buildpackage -us -uc -b -d" >>"$log" 2>&1; }; then
        local why; why=$(grep -iE "error" "$log" | tail -2 | tr '\n' ' ' | cut -c1-200)
        set_status "$name" FAIL "$commit" "build: $why"; return 1
    fi
    local debs="" f
    for f in "$CHROOT"/build/*.deb; do
        case "$f" in *-build-deps_*|*'*'*) ;; *) debs="$debs $f" ;; esac
    done
    [ -n "$debs" ] || { set_status "$name" FAIL "$commit" "no .deb produced"; return 1; }
    # shellcheck disable=SC2086
    mv $debs "$DEST/"
    rm -f "$CHROOT"/build/*.deb "$CHROOT"/build/*.changes "$CHROOT"/build/*.buildinfo "$CHROOT"/build/*.ddeb
    local ver; ver=$(dpkg-parsechangelog -l "$CHROOT$src/debian/changelog" -S Version 2>/dev/null || echo "?")
    set_status "$name" OK "$ver" "$commit"
    rm -rf "$CHROOT$src"
    refresh_repo
}

refresh_repo
retry 3 chroot_run "$CHROOT" apt-get update -qq
fails=0
while read -r name repo branch; do
    case "$name" in ''|'#'*) continue ;; esac
    if [ -n "$ONLY" ] && [ "$ONLY" != "$name" ]; then continue; fi
    if [ -z "$ONLY" ] && grep -q "^$name	OK	" "$STATUS"; then continue; fi
    build_one "$name" "$repo" "$branch" || { fails=$((fails + 1)); warn "$name failed (see $DEST/logs/$name.log)"; }
done < "$LIST"

build_ca_remove "$CHROOT"
log "bridge status:"
column -t -s $'\t' "$STATUS" >&2 || cat "$STATUS" >&2
exit 0
