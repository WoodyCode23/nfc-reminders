# NFC Reminders for Home Assistant

Track recurring chores by scanning an NFC tag or a printed QR code when the chore is done. Home Assistant then tells you what is overdue. Made for things like litter boxes, furnace filters, bathroom cleaning, plant watering and pet medication.

Everything is set up from the Home Assistant screens. There are no helpers to create and no automations to write.

## What it does

- **Scan to mark done.** Scan the tag (or its QR code) with the Home Assistant app and the reminder resets.
- **Or just tap.** Every reminder and group has a Mark done button for your dashboards. No tag needed.
- **QR codes.** Every reminder has a QR code you can print. A sticker works as well as an NFC tag.
- **Overdue overview.** At the times you choose (09:00 and 14:00 by default) you get one notification listing what is overdue, and what is due soon. Nothing due means no notification.
- **Heads-up before it is due.** "Every 5 days, remind after 3": from day 3 it shows as due soon and is in the overview; from day 5 it is overdue.
- **Groups.** Put several reminders in a group, for example "All Litter Boxes". The group's own tag, QR code or button marks all of them done at once.
- **Who did it.** The reminder records who scanned, taken from the phone that scanned.
- **Entities for your own dashboards and automations.** Progress, next due, overdue and more.

## Requirements

- Home Assistant 2026.3 or newer.
- The Home Assistant app on the phones that will scan. iPhone and Android both work.

## Install

### Marketplace (Home Assistant 2026.11 and newer)

Home Assistant's built-in Marketplace replaced HACS. The first time you open it, read and accept its warning.

1. Go to **Settings**, **Marketplace**, and choose **Add from link** in the top right.
2. Enter `https://github.com/WoodyCode23/nfc-reminders` and choose **Add**. If it asks for the type, pick **Integration**.
3. Install **NFC Reminders**.
4. Restart Home Assistant.

To try a beta, open **Settings**, **Devices and services**, **Marketplace**, open the NFC Reminders device, enable its **Pre-release** entity, and switch it on.

### HACS (older Home Assistant)

1. Open HACS.
2. Open the menu in the top right and choose **Custom repositories**.
3. Add `https://github.com/WoodyCode23/nfc-reminders` with the type **Integration**.
4. Find **NFC Reminders** in HACS and choose **Download**.
5. Restart Home Assistant.

### By hand

1. Download the latest release.
2. Copy the `custom_components/nfc_reminders` folder into the `custom_components` folder of your Home Assistant configuration.
3. Restart Home Assistant.

## Add a reminder

1. Go to **Settings**, **Devices and services**, **Add integration**, pick **NFC Reminders**, and choose **A reminder**.
2. Give it a name (for example "Furnace Filter") and say how often it is due (for example every 90 days).
3. Choose how it gets its tag:
   - **Scan an NFC tag now.** Scan the tag with the Home Assistant app, then press Submit.
   - **Pick a tag Home Assistant already knows.** Choose from the list, or type a tag id.
   - **Make a new QR code.** No NFC tag needed. Print the QR code afterwards.

The first time you add a reminder, an entry called **Notifications** appears next to your reminders. That is where you choose who gets told (see below).

## QR codes

Each reminder has a **QR Code** image entity. To print all of them at once, press the **Create printable QR sheet** button on the Notifications entry (or call the `nfc_reminders.create_qr_sheet` action). A notification appears in Home Assistant with a link to a printable page. The link works for one hour.

To scan, point the phone's camera at the code and open the link it shows. The Home Assistant app must be installed on that phone. On an iPhone the app shows a notification that you tap to finish the scan.

The QR code holds the same link Home Assistant writes to NFC tags, so a QR code and an NFC tag for the same reminder are interchangeable.

## Mark done without a tag

Every reminder has a `button.<name>_mark_done` and every group a `button.<group>_mark_done`. Put them on a dashboard and a tap marks the chore done, the same as a scan, and records who tapped. They work in the Home Assistant app on a phone too.

To avoid marking something done by accident, turn on a confirmation in the card: for example a Tile card with `tap_action: {action: toggle, confirmation: true}`, or a Button card with `tap_action: {action: perform-action, perform_action: button.press, target: {entity_id: button.litter_box_1_mark_done}, confirmation: true}`.

## Groups

A group is several reminders that one tag, one QR code or one button marks done together. Use it for "all litter boxes" or "all bathrooms".

1. Add your reminders first.
2. Add the integration again and choose **A group**.
3. Name it and tick its reminders.
4. Give it a tag the same three ways as a reminder: scan one, pick a known one, or make a new QR code.

Each reminder keeps its own tag, so you can still mark one box on its own. A reminder can be in more than one group. Open the group and choose **Configure** to change its reminders or its tags.

A group gets its own entities:

| Entity | What it shows |
|---|---|
| `sensor.<group>_status` | The most urgent status of its reminders: `good`, `warning` or `overdue`. Attributes list the members and which ones are overdue |
| `binary_sensor.<group>_overdue` | On while any of its reminders is overdue |
| `button.<group>_mark_done` | Marks every reminder in the group done |
| `image.<group>_qr_code` | The group's QR code |

Deleting a group never deletes its reminders or their dates. Deleting a reminder simply takes it out of its groups.

## Overdue overview

Open the **Notifications** entry and choose **Configure**:

- **Send the overview at:** 24-hour times separated by commas, for example `09:00, 14:00`.
- **Send it to:** one or more of your notify services or notify entities (phones, groups).
- **Also send a message when something is marked done:** off by default.

Nothing is sent until you choose at least one place to send it. Home Assistant shows a repair notice until you do.

The overview looks like this:

```
2 overdue, 1 due soon
Furnace Filter: 95 days (every 90 days)
Master Bathroom: 21 days (every 20 days)
Litter Box 1: due in 2 days
```

Overdue chores come first, most overdue at the top. Chores past their **Remind after** point come next, soonest first. A reminder that has never been marked done is never counted.

### Remind after

Each reminder has an optional **Remind after**, in the same unit as its interval. Set it when you add the reminder, or later under the reminder's **Configure**. With "every 5 days, remind after 3":

- days 0 to 3: `good`
- day 3 to 5: `warning` (shown as Due soon) and listed in the overview as due soon
- day 5 on: `overdue`

Without it, the status turns to `warning` at the halfway point and the reminder only appears in the overview once it is overdue.

## Entities

Each reminder is a device with these entities:

| Entity | What it shows |
|---|---|
| `sensor.<name>_last_scan` | When it was last done, as text |
| `sensor.<name>_days_since_scan` | Days since it was last done |
| `sensor.<name>_progress` | How far through the interval it is, 0 to 100 percent |
| `sensor.<name>_status` | `good`, `warning` or `overdue`, as a state to trigger automations on |
| `sensor.<name>_next_due` | When it is next due |
| `sensor.<name>_last_done_by` | Who did it last |
| `binary_sensor.<name>_overdue` | On when it is overdue |
| `button.<name>_mark_done` | Marks it done without a scan |
| `image.<name>_qr_code` | Its QR code |

The progress sensor has these attributes: `status` (the same value as the status sensor), `interval`, `interval_unit`, `remind_after`, `nfc_tag_id` (the first tag) and `tag_ids` (all tags).

## Use it in your own automations

The status is a real state, so anything in Home Assistant can react to it. For example, turn a light red when a litter box becomes overdue:

```yaml
triggers:
  - trigger: state
    entity_id: sensor.litter_box_1_status
    to: overdue
actions:
  - action: light.turn_on
    target:
      entity_id: light.hallway
    data:
      color_name: red
```

The status is `good` at first, `warning` from the **Remind after** point (or from halfway when there is none), and `overdue` once it is due. It goes back to `good` when the tag is scanned. `binary_sensor.<name>_overdue` gives the same thing as a plain on or off.

## Actions

`nfc_reminders.mark_done` marks reminders done, the same as a scan. Give it any entity of a reminder, or of a group to mark all of the group's reminders.

```yaml
action: nfc_reminders.mark_done
data:
  entity_id: sensor.furnace_filter_progress
  # Optional. Leave out for "now".
  when: "2026-11-01 08:30:00"
```

`nfc_reminders.create_qr_sheet` creates the link to the printable QR sheet. Groups are on it too, marked "Group".

## Change or delete a reminder

Open the reminder under **Settings**, **Devices and services**, **NFC Reminders** and choose **Configure** to change how often it is due or which tags mark it done. Changes take effect straight away. Delete it from the same place.

## Upgrading from version 1

Version 1 kept the last scan in `input_datetime` helpers that you had to create yourself. Version 2 keeps it inside the integration.

- Your reminders, their entity ids and their history are kept.
- The first time version 2 starts, it reads each reminder's last scan from `input_datetime.<name>_last_scan` (and who did it from `input_text.<name>_last_cleaned_by`) once.
- Your helpers and any automations you wrote are never changed. Once you are happy with version 2 you can remove them yourself.
- If your own automation handled "master" tags that mark several reminders, make a group for each instead and pick that tag under **Pick a tag Home Assistant already knows**.
- If you had your own automation that set the helpers on a scan, it keeps working but is no longer needed. Switch it off when you turn on the built-in notifications, so you do not get two messages.
- The `status` attribute now says `overdue` only once the reminder is actually due (it used to say so from 80 percent).
- A reminder that has never been scanned now shows days since as unknown (it used to show 99).

## Troubleshooting

**A scan does nothing.** Go to **Developer tools**, **Events**, listen to `tag_scanned` and scan again. If no event shows up, the problem is between the phone and Home Assistant: check that the Home Assistant app is installed and signed in on that phone. If an event does show up, compare its `tag_id` with the tags listed under the reminder's **Configure**.

**No overdue notification arrives.** Check that the Notifications entry has at least one place to send to, and look in the Home Assistant log for a warning that names a notify service that no longer exists.

**The QR code opens a web page.** The phone does not have the Home Assistant app, or it is not signed in.

## Contributing

Issues and pull requests are welcome at [github.com/WoodyCode23/nfc-reminders](https://github.com/WoodyCode23/nfc-reminders/issues).

To run the tests:

```
pip install -r requirements_test.txt
pytest
```

## License

MIT. See the LICENSE file.
