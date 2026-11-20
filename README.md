# Helmet library loans for Home Assistant

Shows your [Helmet](https://helmet.finna.fi/) library loans with due dates, and
reservations that are ready for pickup, as Home Assistant sensors. Add it once per
library card, so a whole family can be followed on one dashboard.

> Unofficial. Not affiliated with or endorsed by the Helmet libraries or the National
> Library of Finland.

## How it works

Every 6 hours the integration signs in to helmet.finna.fi with the card number and PIN,
reads the "Checked out items" and "Holds" pages, and signs out. Helmet has no public
API for personal loan data, so a redesign of those pages can break the lists. The
counts come from a separate site endpoint and usually keep working; Home Assistant
logs a warning when the counts and the lists disagree.

The card number and PIN are stored only in your Home Assistant configuration and are
sent only to helmet.finna.fi.

## Install

### HACS (custom repository)

1. HACS → ⋮ → Custom repositories → add `https://github.com/Crare/ha-helmet`,
   type **Integration**.
2. Search for **Helmet library loans** in HACS and download it.
3. Restart Home Assistant.

### Manual

Copy `custom_components/helmet` into your Home Assistant `config/custom_components/`
folder (so you have `config/custom_components/helmet/manifest.json`) and restart.

## Setup

Settings → Devices & services → Add integration → **Helmet library loans**. Enter a
name (for example the person's first name), the library card number and PIN.
Repeat for each library card.

If a PIN changes, Home Assistant asks for the new one under Settings → Repairs.

## Sensors (per card)

Entity IDs follow the name you gave, e.g. `sensor.anna_loans`.

| Sensor | State | Attributes |
| --- | --- | --- |
| Loans | number of loans | `loans`: list of `title`, `due_date`, soonest first |
| Next due date | earliest due date | |
| Overdue | number of overdue loans | |
| Reservations | number of reservations | `holds`: list of `title`, `ready`, `pickup_by`, ready ones first |
| Ready for pickup | reservations waiting at the library | `holds`: list of `title`, `pickup_by`; `waiting`: reservations still in the queue |
| Next pickup deadline | earliest last pickup day | |

## Dashboard cards

Two ready-made Markdown cards are in [`dashboard/`](dashboard):

- [`loans-card.yaml`](dashboard/loans-card.yaml): each person's loans with due date
  and days left (🟠 within 3 days, 🔴 overdue).
- [`reservations-card.yaml`](dashboard/reservations-card.yaml): each person's
  reservations, ready ones first with the last pickup day.

To add one: Edit dashboard → Add card → **Manual** and paste the file's contents.
No editing needed: the cards find every Helmet library card added to Home Assistant
and use each card's name as the heading.

## Notification when a reservation is ready

Replace the entity and the notify action with your own:

```yaml
alias: Helmet reservation ready for pickup
triggers:
  - trigger: state
    entity_id: sensor.anna_ready_for_pickup
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.state | int(0) > trigger.from_state.state | int(0) }}"
actions:
  - action: notify.mobile_app_your_phone
    data:
      message: "A Helmet reservation is ready for pickup for Anna."
```

## Reporting a problem

To check a card outside Home Assistant, run the check script on your own computer.
It asks for the card number and PIN without showing them and prints only whether
the login worked and how many items it read, which is safe to share:

```bash
python3 -m venv .venv
.venv/bin/pip install aiohttp beautifulsoup4
.venv/bin/python scripts/check_login.py
```

If the lists are empty or wrong, open an issue with that output or the warning from
the Home Assistant log. **Never post your card number, PIN or saved pages that contain your
name or loans.**

## Development

```bash
python -m pip install beautifulsoup4 pytest
python -m pytest tests
```

## License

MIT. See [LICENSE](LICENSE).
