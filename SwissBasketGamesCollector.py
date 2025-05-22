import requests
import pandas as pd
import json
import io
import os
import datetime
from pathlib import Path
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import numpy as np

# Create logs directory
logs_dir = Path(os.path.dirname(os.path.abspath(__file__))) / "logs"
logs_dir.mkdir(parents=True, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(logs_dir / "games_collector.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("SwissBasketGamesCollector")

class Settings:
    def __init__(self, settings_path='settings.json'):
        self.settings_path = settings_path
        self._data = self.load_settings()

    def load_settings(self):
        """Load settings from settings.json file."""
        try:
            with open(self.settings_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading settings: {str(e)}")
            raise

    def save_settings(self):
        """Save settings to settings.json file."""
        try:
            with open(self.settings_path, 'w') as f:
                json.dump(self._data, f, indent=2)
            logger.info("Settings saved successfully")
        except Exception as e:
            logger.error(f"Error saving settings: {str(e)}")
            raise
        
    def get(self, key, default=None):
        """Get a top-level setting with a default value."""
        return self._data.get(key, default)

def download_team_games(team_id):
    """Download the Excel data for a team directly using the team ID"""
    try:
        export_url = f"https://www.basketplan.ch/exportTeamGames.do?teamId={team_id}"
        logger.info(f"Downloading Excel from: {export_url}")
        response = requests.get(export_url)
        response.raise_for_status()
        return response.content
    except Exception as e:
        logger.error(f"Error downloading Excel: {str(e)}")
        raise

def get_google_services(credentials_path='credentials.json'):
    """Authenticate and get Google Sheets and Drive services"""
    try:
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path, 
            scopes=['https://www.googleapis.com/auth/spreadsheets', 
                    'https://www.googleapis.com/auth/drive'])
        sheets_service = build('sheets', 'v4', credentials=credentials)
        drive_service = build('drive', 'v3', credentials=credentials)
        return sheets_service, drive_service
    except Exception as e:
        logger.error(f"Error authenticating with Google: {str(e)}")
        raise

def get_spreadsheet_id(drive_service, sheets_service, settings : Settings):
    """Get spreadsheet ID from settings, verify it exists, or create a new one"""
    try:
        # Load settings
        spreadsheet_id = settings.get('googleSheets', {}).get('spreadsheetId', '')
        spreadsheet_name = settings.get('googleSheets', {}).get('spreadsheetName', 'BasketPlan Games')
        
        # Step 1: Check if spreadsheet ID exists in settings and is valid
        if spreadsheet_id:
            try:
                # Check if the spreadsheet exists
                sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
                logger.info(f"Using existing spreadsheet ID from settings: {spreadsheet_id}")
                return spreadsheet_id
            except HttpError:
                logger.warning(f"Spreadsheet ID {spreadsheet_id} from settings not found or not accessible")
                # Continue to step 2
        
        # Step 2: Check if spreadsheet with given name exists
        results = drive_service.files().list(
            q=f"name='{spreadsheet_name}' and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
            spaces='drive'
        ).execute()
        
        files = results.get('files', [])
        
        if files:
            spreadsheet_id = files[0]['id']
            logger.info(f"Found existing spreadsheet by name: {spreadsheet_name}, ID: {spreadsheet_id}")
            
            # Update settings with the found ID and name
            if not settings.get('googleSheets'):
                settings._data['googleSheets'] = {}
            settings._data['googleSheets']['spreadsheetId'] = spreadsheet_id
            settings._data['googleSheets']['spreadsheetName'] = spreadsheet_name
            settings.save_settings()
            
            return spreadsheet_id
        
        # Step 3: Create a new spreadsheet
        logger.info(f"Creating new spreadsheet: {spreadsheet_name}")
        spreadsheet_body = {
            'properties': {
                'title': spreadsheet_name
            }
        }
        
        spreadsheet = sheets_service.spreadsheets().create(body=spreadsheet_body).execute()
        spreadsheet_id = spreadsheet['spreadsheetId']
        
        # Update settings with the new ID and name
        if not settings.get('googleSheets'):
            settings._data['googleSheets'] = {}
        settings._data['googleSheets']['spreadsheetId'] = spreadsheet_id
        settings._data['googleSheets']['spreadsheetName'] = spreadsheet_name
        settings.save_settings()
        
        return spreadsheet_id
    except Exception as e:
        logger.error(f"Error getting or creating spreadsheet: {str(e)}")
        raise

def share_spreadsheet(drive_service, spreadsheet_id, email):
    """Share the spreadsheet with users in settings.json"""
    try:
        user_permission = {
            'type': 'user',
            'role': 'writer',
            'emailAddress': email
        }
        
        drive_service.permissions().create(
            fileId=spreadsheet_id,
            body=user_permission,
            fields='id',
            sendNotificationEmail=False
        ).execute()
        
        logger.info(f"Shared spreadsheet with {email}")
    except Exception as e:
        logger.error(f"Error sharing spreadsheet with {email}: {str(e)}")
        # Continue with next user even if sharing with one fails

def update_sheet(sheets_service, spreadsheet_id, sheet_name, df):
    """Update a sheet with dataframe content while preserving column order"""
    try:
        # Check if sheet exists, if not create it
        try:
            sheets_service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                ranges=f"{sheet_name}!A1"
            ).execute()
        except HttpError as e:
            if e.resp.status == 400 or e.resp.status == 404:
                # Add new sheet
                request_body = {
                    'requests': [{
                        'addSheet': {
                            'properties': {
                                'title': sheet_name
                            }
                        }
                    }]
                }
                sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body=request_body
                ).execute()
                logger.info(f"Created new sheet: {sheet_name}")
            else:
                raise
        
        # Replace NaN with empty string
        df = df.replace({np.nan: ''})
        
        # Convert timestamp columns to strings
        for col in df.select_dtypes(include=['datetime64', 'datetime64[ns]']).columns:
            df[col] = df[col].dt.strftime('%Y-%m-%d')
            
        # Convert time columns to strings
        for col in df.select_dtypes(include=['timedelta64[ns]']).columns:
            df[col] = df[col].astype(str)
        
        # Handle any remaining datetime.time objects
        for col in df.columns:
            if df[col].apply(lambda x: isinstance(x, datetime.time)).any():
                df[col] = df[col].apply(lambda x: x.strftime('%H:%M') if isinstance(x, datetime.time) else x)
        
        # Check if we need to reorder columns
        # Get existing columns from the sheet
        existing_columns = []
        sheet_header = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1:Z1"
        ).execute()
            
        # Get current columns from the sheet
        if 'values' in sheet_header and sheet_header['values']:
            existing_columns = sheet_header['values'][0]
                
        if existing_columns:
            # Get common columns that exist in both the existing sheet and the DataFrame
            common_columns = [col for col in existing_columns if col in df.columns]
            
            # Get columns that only exist in the DataFrame but not in the existing sheet
            new_columns = [col for col in df.columns if col not in common_columns]
            
            # Reorder DataFrame: first use existing columns in their original order, then add new columns
            if common_columns:
                df = df[common_columns + new_columns]
                logger.info(f"Reordered columns to match existing sheet.")
        
        # Convert to values list
        values = [df.columns.tolist()] + df.values.tolist()
                
        # Clear existing content
        sheets_service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1:Z50000"
        ).execute()
        
        # Update sheet with data
        result = sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, 
            range=f"{sheet_name}!A1", 
            valueInputOption='RAW',
            body={'values': values}
        ).execute()
        
        logger.info(f"Updated sheet: {sheet_name} with {result.get('updatedCells')} cells")
    except Exception as e:
        logger.error(f"Error updating sheet {sheet_name}: {str(e)}")
        raise

def main():
    try:
        # Load settings
        settings = Settings()
        
        # Load team data from settings
        teams = settings.get('teams', {})
        if not teams:
            logger.error("No teams found in settings.json")
            return
        
        # Get Google Sheets service
        sheets_service, drive_service = get_google_services()
        
        # Get or create spreadsheet using settings
        spreadsheet_id = get_spreadsheet_id(drive_service, sheets_service, settings)
        
        # Share spreadsheet with users from settings
        users = settings.get('googleSheets', {}).get('writePrivilege', [])
        for email in users:
            share_spreadsheet(drive_service, spreadsheet_id, email)
        
        # Create a list to hold all dataframes for the combined sheet
        all_games = []
        
        # Process each team
        for team_name, team_data in teams.items():
            logger.info(f"Processing team: {team_name}")
            
            try:
                # Check if team ID is valid
                team_id = team_data.get('id', '')
                if not team_id:
                    logger.warning(f"Skipping team {team_name}: No team ID provided")
                    continue
                
                # Download Excel content directly
                excel_content = download_team_games(team_id)
                
                # Read the Excel data
                df = pd.read_excel(io.BytesIO(excel_content))
                
                # Add a column to identify the team
                df['Team'] = team_name
                
                # Add the week number
                if 'Datum' in df.columns:
                    df['Week'] = df['Datum'].dt.isocalendar().week
                
                # Append to the list of all games
                all_games.append(df)
                
                # Update sheet for this team
                sheet_name = team_name[:24]  # Sheet names limited to 24 chars in Google Sheets
                update_sheet(sheets_service, spreadsheet_id, sheet_name, df)
                
                logger.info(f"Added sheet for team {team_name}")
            except Exception as e:
                logger.error(f"Error processing team {team_name}: {str(e)}")
                continue
        
        # Create combined "All" sheet with all games
        if all_games:
            logger.info("Creating combined 'All' sheet with all games")
            combined_df = pd.concat(all_games, ignore_index=True)
            
            if "Datum" in combined_df.columns:
                # Sort by date
                combined_df = combined_df.sort_values(by="Datum")
            
            # Update "All" sheet
            update_sheet(sheets_service, spreadsheet_id, "All", combined_df)
            logger.info(f"Added combined 'All' sheet with {len(combined_df)} games")
        
        spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        logger.info(f"Google Sheet updated: {spreadsheet_url}")
        print(f"Google Sheet updated: {spreadsheet_url}")
        
    except Exception as e:
        logger.error(f"Script execution failed: {str(e)}")
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
