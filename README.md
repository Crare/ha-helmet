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
| Ready for pickup | reservations waiting at the library | `holds`: list of `title`, `pickup_by`; `waiting`: reservations still in the queue |
| Next pickup deadline | earliest last pickup day | |

## Dashboard card

Add a Markdown card (Edit dashboard → Add card → Markdown) and paste the following.
Change the names in `people` to match your sensors' entity IDs.

```jinja
{% set people = ['anna', 'mikko', 'ella'] %}
{% for p in people %}
## {{ p | capitalize }}
{% set ready = state_attr('sensor.' ~ p ~ '_ready_for_pickup', 'holds') or [] %}
{% if ready %}
**Ready for pickup**
{% for h in ready %}
- 📚 {{ h.title }}{% if h.pickup_by %} — pick up by {{ as_timestamp(h.pickup_by) | timestamp_custom('%-d.%-m.') }}{% endif %}
{% endfor %}
{% endif %}
{% set loans = state_attr('sensor.' ~ p ~ '_loans', 'loans') or [] %}
**Loans ({{ loans | count }})**
{% for l in loans %}
{% set days = ((as_timestamp(l.due_date) - as_timestamp(today_at())) / 86400) | round(0) | int if l.due_date else none %}
- {{ l.title }}{% if l.due_date %} — due {{ as_timestamp(l.due_date) | timestamp_custom('%-d.%-m.') }}{% if days is not none and days <= 3 %} ⚠️{% endif %}{% endif %}
{% else %}
- No loans
{% endfor %}
{% endfor %}
```

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

If the lists are empty or wrong, open an issue with the warning from the Home
Assistant log. **Never post your card number, PIN or saved pages that contain your
name or loans.**

## Development

```bash
python -m pip install beautifulsoup4 pytest
python -m pytest tests
```
