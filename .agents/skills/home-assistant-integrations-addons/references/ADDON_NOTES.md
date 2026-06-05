# Add-on Notes

## Source of truth (official docs)

The **Home Assistant "Apps" (formerly add-ons) developer documentation** is the authoritative reference for everything in this add-on:

**https://developers.home-assistant.io/docs/apps/**

Relevant sub-pages for the `ipbuilding_gateway` add-on in this repo:

| Topic | Doc page |
|-------|----------|
| Manifest / `config.yaml` schema | [Configuration](https://developers.home-assistant.io/docs/apps/configuration) |
| Supervisor communication / add-on API | [Communication](https://developers.home-assistant.io/docs/apps/communication) |
| Local test rig (Docker) | [Local Testing](https://developers.home-assistant.io/docs/apps/testing) |
| Publishing to `ghcr.io` / add-on repos | [Publishing](https://developers.home-assistant.io/docs/apps/publishing) |
| Repo layout, `repository.yaml`, `DOCS.md`, `config.yaml` | [Repositories](https://developers.home-assistant.io/docs/apps/repository) |
| Security model (`host_network`, `privileged`, `init`) | [Security](https://developers.home-assistant.io/docs/apps/security) |
| First-time authoring walkthrough | [Tutorial: Making your first app](https://developers.home-assistant.io/docs/apps/tutorial) |

**When this skill and the official docs disagree, the official docs win.** Open an issue or update the skill if the skill is stale.

## Availability

- Add-ons are available only on Home Assistant OS or Supervised installs.

## Troubleshooting

- If an add-on is missing, verify install type and repositories.
- Use `ha_get_addon` to list installed add-ons and status.

## Example (official docs)

Add-on install entry point from the official Add-ons docs:

```text
Settings > Add-ons > Add-on store
```
