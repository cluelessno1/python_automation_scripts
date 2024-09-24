
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
def connect_with_people(search_url):
    print("Navigating to the search results page...")
    driver.get(search_url)
    time.sleep(SLEEP_COUNT_IN_SECS)
    
    try:
        # Get all connection buttons
        connect_buttons = driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'Invite')]")
        for button in connect_buttons:
            connect_with_single_person(button)
        print("Finished sending connection requests on the current page.")
    except Exception as e:
        print(f"Error during connecting with people: {e}")

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
        custom_message = f"Hi {name},<your message>"
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