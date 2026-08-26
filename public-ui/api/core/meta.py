"""Everything the SPA needs to render itself without hardcoding a single
category, city, spec field, or channel. values.yaml stays the source of
truth; availability comes from live config so the UI can never offer a
sign-in button or a notification channel that isn't wired up."""
from . import leadfilter, notify, oauth, specs, tables, values


def get_meta() -> dict:
    version = tables.get_entity(tables.TABLE_VERSIONS, "pipeline", "config") or {}
    required = values.required_fields()
    return {
        "categories": values.categories(),
        "cities": leadfilter.city_options(),
        "hoa_states": [
            {"id": "zero", "label": "No HOA / $0"},
            {"id": "none", "label": "HOA not mentioned"},
            {"id": "has", "label": "Has an HOA fee"},
        ],
        # per-category required fields drive "which specs can I filter on"
        "required_fields": required,
        "spec_fields": [
            {
                "id": field,
                "kind": specs.field_kind(field),
                "options": specs.enum_options(field),
                # which categories treat this field as required, so the
                # builder can grey out specs that don't apply to a selection
                "categories": [c for c, fs in required.items() if field in fs],
            }
            for field in specs.known_fields()
        ],
        "channels": notify.available_channels(),
        "oauth_providers": oauth.available(),
        "pipeline": {
            "status": version.get("status", "unknown"),
            "deployed_at": version.get("deployed_at", ""),
        },
    }
