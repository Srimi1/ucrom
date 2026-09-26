"""Stand-in for AOSP's gki module, which Ubuntu's mkbootimg package imports
but does not ship. It is only used to sign GKI (boot header v4) images;
ucrom's phones that use header <= 3 never call it."""


def generate_gki_certificate(*_args, **_kwargs):
    raise SystemExit("GKI boot signatures are not supported by this mkbootimg build")
