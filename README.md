# Swiss Basket Games Collector

## Overview
SwissBasketGamesCollector is a Python utility that automatically collects basketball game schedules from the Swiss Basketball Federation's website (basketplan.ch) for multiple teams and organizes them into a Google Sheets document. This tool helps basketball clubs, coaches, and team managers keep track of upcoming games and past scores across different teams in one centralized location.

## Features
- Automatically fetches game schedules from basketplan.ch by team ID
- Organizes games into separate sheets per team in Google Sheets
- Creates a consolidated view of all games in one sheet
- Automatic sharing on Google Sheets with designated Google users

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/maximecharriere/SwissBasketGamesCollector.git
   cd SwissBasketGamesCollector
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up Google Sheets API credentials:

   > To use this tool, you'll need to set up a Google Cloud project with a service account. Follow the official Google documentation:  
   > [Creating and managing service account keys](https://cloud.google.com/iam/docs/creating-managing-service-account-keys)

   - Create a Google Cloud project
   - Enable the Google Sheets and Google Drive APIs
   - Create a service account and download the credentials as `credentials.json`
   - Place the `credentials.json` file in the project root directory

4. Configure your `settings.json` file (see template below)

## Settings Template

Create a `settings.json` file in the project root with the following structure:

```json
{
  "googleSheets": {
    "spreadsheetId": "",
    "spreadsheetName": "YourClub_Games",
    "writePrivilege": [
      "your.email@example.com"
    ]
  },
  "teams": {
    "Team1Name": {
      "id": "1234"
    },
    "Team2Name": {
      "id": "5678"
    },
    "Team3Name": {
      "id": "9012"
    }
    // Add more teams as needed
  }
}
```

Notes:
- Leave `spreadsheetId` empty if you want the script to create a new spreadsheet
- Provide the basketplan.ch team IDs for each team you want to track
- Add email addresses to `writePrivilege` to automatically add write privilege to these Google users

## Usage

Run the script:

```sh
python SwissBasketGamesCollector.py
```

## How It Works

The script performs the following operations:

1. **Load Configuration**: Reads team IDs and Google Sheets settings from `settings.json`

2. **Google Authentication**: Connects to Google Sheets and Drive APIs using service account credentials

3. **Spreadsheet Management**: Uses existing spreadsheet of create a new one if none exists

4. **Permission Management**: Shares the spreadsheet with users specified in settings

5. **Data Collection**: For each team configured in settings:
   - Downloads game data from basketplan.ch using the team ID
   - Adds team name and calculates week numbers
   - Updates the team's dedicated sheet in the spreadsheet

6. **Data Consolidation**: Creates/updates an "All" sheet with games from all teams sorted by date

7. **Logging**: Records all operations to both console and log file in the `logs` directory

