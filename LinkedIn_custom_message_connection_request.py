
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time

# Replace these with your LinkedIn credentials
linkedin_username = ''
linkedin_password = ''
linkedin_login_url = 'https://www.linkedin.com/login'
linkedin_peoples_search_page_url = 'https://www.linkedin.com/search/results/people/?currentCompany=%5B%223185%22%5D&keywords=senior%20engineer&origin=FACETED_SEARCH&page=2&sid=E!Q'
SLEEP_COUNT_IN_SECS = 5
CUSTOM_MESSAGE_TO_BE_SENT_IN_THE_CONNECTION_INVITE = "\n\nI'm Shashwat, a software engineer at Qualcomm specializing in automation, AWS migration, and backend development. Looking forward to connect!\n\nRegards,\nShashwat"
# Maximum connection requests to try to send in one session
MAX_CONNECTION_SENT_COUNT = 20
# Maxiumum search pages to iterate through
MAX_PAGES_COUNT = 10

# Function to log into LinkedIn
def linkedin_login(username, password):
    print("Attempting to log into LinkedIn...")
    driver.get(linkedin_login_url)

    try:
        username_input = driver.find_element(By.ID, 'username')
        username_input.send_keys(username)
        password_input = driver.find_element(By.ID, 'password')
        password_input.send_keys(password)
        password_input.send_keys(Keys.RETURN)
        time.sleep(SLEEP_COUNT_IN_SECS)

        # Check if login is successful
        if "feed" in driver.current_url:
            print("Login successful!")
        else:
            print("Login failed. Please check credentials or CAPTCHA.")
            driver.quit()
            return False
    except Exception as e:
        print(f"Error during login: {e}")
        driver.quit()
        return False
    return True

# Function to clean the LinkedIn search page URL
def parse_linkedin_peoples_search_page_url(url):
    print("Parsing the LinkedIn search page URL...")
    if '&page=' in url:
        url = url.split('&page=')[0]
    print(f"Cleaned URL: {url}")
    return url

# Function to connect with people
def connect_with_people(search_url, max_connection_sent_count=MAX_CONNECTION_SENT_COUNT, max_pages=MAX_PAGES_COUNT, stop_message="No results found"):

    page = 1
    connection_sent_count = 0
    while page <= max_pages and connection_sent_count < max_connection_sent_count:
        # Append the current page number to the URL
        paginated_url = f"{search_url}&page={page}"
        print(f"Processing page {page}: {paginated_url}")
        
        # Open the LinkedIn People Search page URL
        driver.get(paginated_url)
        time.sleep(SLEEP_COUNT_IN_SECS)  # Wait for the page to load

        # Check for the stop message indicating the end of results
        try:
            # Locate the element with the message (you can modify the XPath to match the actual message element)
            stop_element = driver.find_element(By.XPATH, f"//*[contains(text(), '{stop_message}')]")
            print("Stop message found, exiting...")
            break  # Exit the loop if the stop message is found
        except:
            print(f"No stop message on page {page}, continuing...")

        try:
            # Get all connection buttons
            connect_buttons = driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'Invite')]")
            for button in connect_buttons:
                connect_with_single_person(button)
            print("Finished sending connection requests on the current page.")
            connection_sent_count += 1
        except Exception as e:
            print(f"Error during connecting with people: {e}")

        
        # Move to the next page
        page += 1

# Function to connect with a single person
def connect_with_single_person(button):
    try:
        button_aria_label = button.get_attribute('aria-label')
        name = button_aria_label[button_aria_label.index("Invite") + len("Invite"):button_aria_label.index("to connect")].strip()
        print(f"Sending connection request to {name}...")
        
        button.click()
        time.sleep(SLEEP_COUNT_IN_SECS)

        # Click on "Add a note"
        add_a_note_button = driver.find_element(By.XPATH, "//button[contains(@aria-label, 'Add a note')]")
        add_a_note_button.click()
        time.sleep(SLEEP_COUNT_IN_SECS)
        
        enter_custom_message(name)

    except Exception as e:
        print(f"Error occurred while connecting with {name}: {e}")

# Function to enter a custom message in the textarea
def enter_custom_message(name):
    try:
        custom_message = f"Hi {name}, {CUSTOM_MESSAGE_TO_BE_SENT_IN_THE_CONNECTION_INVITE}"
        textarea = driver.find_element(By.ID, 'custom-message')
        textarea.clear()
        textarea.send_keys(custom_message)
        print(f"Custom message for {name} entered successfully.")

        send_invitation_button = driver.find_element(By.XPATH, "//button[contains(@aria-label, 'Send invitation')]")
        send_invitation_button.click()
        print(f"Invitation sent to {name}.")
        time.sleep(SLEEP_COUNT_IN_SECS)
        
    except Exception as e:
        print(f"Error while entering custom message for {name}: {e}")

# Main logic
if __name__ == "__main__":
    driver = webdriver.Chrome()  # Initialize WebDriver inside main

    if linkedin_login(linkedin_username, linkedin_password):
        linkedin_peoples_search_page_url = parse_linkedin_peoples_search_page_url(linkedin_peoples_search_page_url)
        connect_with_people(linkedin_peoples_search_page_url)
    
    print("Closing browser...")
    driver.quit()