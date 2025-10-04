NFC Reminders for Home Assistant
Show Image
Show Image

A Home Assistant custom integration that makes it easy to track recurring tasks using NFC tags. Perfect for tracking litter box cleanings, furnace filter changes, bathroom cleanings, and any other routine maintenance tasks!

Features
✨ Easy UI Configuration - Add reminders through the Home Assistant UI, no YAML editing required

📱 NFC Tag Scanning - Automatically tracks when you scan an NFC tag

⏰ Flexible Intervals - Set reminders for minutes, hours, or days

📊 Multiple Sensors - Get formatted timestamps, days since last scan, and progress percentages

🎨 Works with Custom Cards - Integrates seamlessly with Lovelace dashboard cards

Screenshots
(Add screenshots here of the integration setup and your custom card)

Installation
HACS (Recommended)
Open HACS
Go to "Integrations"
Click the three dots in the top right
Select "Custom repositories"
Add this repository URL: https://github.com/WoodyCode23/nfc-reminders
Category: Integration
Click "Add"
Search for "NFC Reminders"
Click "Download"
Restart Home Assistant
Manual Installation
Download the latest release
Extract the ZIP file
Copy the custom_components/nfc_reminders folder to your Home Assistant's custom_components directory
Restart Home Assistant
Setup
Add a Reminder
Go to Settings → Devices & Services
Click + Add Integration
Search for "NFC Reminders"
Fill out the form:
Reminder Name: e.g., "Furnace Filter"
NFC Tag ID: Your NFC tag ID (scan a tag first to see the ID in notifications)
Interval: e.g., 90
Interval Unit: Choose days, hours, or minutes
Click Submit
That's it! The integration will automatically create all the necessary helper entities for you. No YAML editing required!

Scan Your NFC Tag
Once configured, simply scan your NFC tag near your Home Assistant device. The integration will automatically update the timestamp!

What Gets Created
For each reminder, the integration creates three sensors:

sensor.{name}_last_scan - Formatted date/time of last scan
sensor.{name}_days_since_scan - Number of days since last scan
sensor.{name}_progress - Progress percentage (0-100%)
The progress sensor also includes helpful attributes:

status: "good", "warning", or "overdue"
interval: Your configured interval
interval_unit: Your configured unit
nfc_tag_id: The NFC tag ID
Usage with Custom Cards
This integration works great with custom Lovelace cards. Here's an example configuration:

yaml
type: custom:nfc-reminder-card
use_home_assistant_storage: true
reminders:
  - name: "Furnace Filter"
    entity_id: input_datetime.furnace_filter_last_scan
    person_entity_id: input_text.furnace_filter_last_changed_by
    nfc_tag: "your-nfc-tag-id"
    interval: 90
    unit: "days"
  - name: "Litter Box 1"
    entity_id: input_datetime.litter_box_1_last_scan
    person_entity_id: input_text.litter_box_1_last_cleaned_by
    nfc_tag: "another-tag-id"
    interval: 2
    unit: "days"
Examples
Common Use Cases
Furnace Filter Changes:

Interval: 90 days
Scan the NFC tag on your furnace whenever you change the filter
Litter Box Cleanings:

Interval: 1-2 days
Place NFC tags on or near each litter box
Bathroom Cleanings:

Interval: 7 days
NFC tags in each bathroom
Plant Watering:

Interval: 3-7 days
NFC tags on plant pots
Pet Medication:

Interval: 12 hours
NFC tag on medication bottle
Managing Reminders
Edit a Reminder
Go to Settings → Devices & Services
Find NFC Reminders
Click on the reminder you want to edit
Click Configure
Update the interval settings
Delete a Reminder
Go to Settings → Devices & Services
Find NFC Reminders
Click on the reminder
Click the trash icon
Confirm deletion
Troubleshooting
Integration doesn't appear in the list:

Ensure all files are in /config/custom_components/nfc_reminders/
Restart Home Assistant completely
Check Configuration → Logs for any errors
NFC tag scans don't update the timestamp:

Verify the tag ID matches exactly (check notifications when you scan)
Ensure the input_datetime helper entity exists
Go to Developer Tools → Events and listen to tag_scanned to see if events are firing
Sensors show "Unknown":

Make sure the integration created the input_datetime helper automatically
Scan the NFC tag at least once
Verify entity names match (check Settings → Devices & Services → Entities)
Contributing
Contributions are welcome! Please feel free to submit a Pull Request.

License
MIT License - see LICENSE file for details

Credits
Created for the Home Assistant community

Support
If you find this integration helpful, please ⭐ star this repo!

For issues or feature requests, please open an issue.

