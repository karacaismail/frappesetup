app_name = "platform_core"
app_title = "Platform Core"
app_publisher = "Platform"
app_description = "Platform backend modules"
app_email = "noreply@example.test"
app_license = "mit"

# Mobile sync tables must exist before the sequence row is created.
after_install = "platform_core.mobil.store.seed_sequence"
after_migrate = "platform_core.mobil.store.seed_sequence"
