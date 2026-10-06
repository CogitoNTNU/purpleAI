# VulnShop target

A deliberately vulnerable Flask shop for the two-PC lab. The defender reverse
proxy checks requests before forwarding them here. See
[VULNERABILITIES.md](VULNERABILITIES.md) for the planted vulnerabilities.

Use the [sandbox guide](../../../deploy/sandbox/README.md) to run the target on
BlueAI. The shared sandbox Dockerfile supplies its dependencies. This folder
contains the application, templates, styling, and sample files used by the lab.

VulnShop listens on port 5000 inside its internal Docker network. Access it through
the defender at `http://BLUE_IP:8080` from RedAI or the configured gamehost,
replacing `BLUE_IP` with BlueAI's
configured address. The target's port is not published.

SQLite data, uploads and runtime reports use temporary container storage and are
discarded when the stack stops. `VULNSHOP_DB_PATH` selects the SQLite location;
the sandbox sets it to `/data/vulnshop.db`. Use synthetic data only.
