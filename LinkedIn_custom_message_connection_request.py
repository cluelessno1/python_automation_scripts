from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import asyncio

# Replace these with your LinkedIn credentials
linkedin_username = ''
linkedin_password = ''
linkedin_login_url = 'https://www.linkedin.com/login'
linkedin_peoples_search_page_url = 'https://www.linkedin.com/search/results/people/?currentCompany=%5B%221441%22%5D&geoUrn=%5B%22102713980%22%5D&keywords=senior%20engineer&origin=FACETED_SEARCH'

# Function to log into LinkedIn
def linkedin_login(username, password):    
    # Open LinkedIn login page
    driver.get(linkedin_login_url)

    # Find and fill in the username field
    username_input = driver.find_element(By.ID, 'username')
    username_input.send_keys(username)

    # Find and fill in the password field
    password_input = driver.find_element(By.ID, 'password')
    password_input.send_keys(password)

    # Submit the form (login)
    password_input.send_keys(Keys.RETURN)

    # Wait for a few seconds for the page to load
    time.sleep(10)

    # Optionally, you can check if login was successful (for example, by checking URL or page content)
    if "feed" in driver.current_url:
        print("Login successful")
    else:
        print("Login failed, please check your credentials or CAPTCHA")


# This function will remove '&page=' from the linkedin search page url provided by the user,
# so that we can append it ourselves in the func connect_with_people and parse through multiple pages iteratively
def parse_linkedin_peoples_search_page_url(linkedin_peoples_search_page_url):
    if '&page=' in linkedin_peoples_search_page_url:
        startIndex = linkedin_peoples_search_page_url.index('&page=')
        prefix = linkedin_peoples_search_page_url[:startIndex]
        n = len('&page=')
        temp = linkedin_peoples_search_page_url[startIndex+n:]
        secondStartIndex = temp.index('&')
        suffix = temp[secondStartIndex:]
        linkedin_peoples_search_page_url = prefix + suffix
    print(f"Cleaned new search page url is : {linkedin_peoples_search_page_url}")
    return linkedin_peoples_search_page_url


# Function to connect with people iteratively across pages
async def connect_with_people(search_page_url, max_pages=5, stop_message="No results found"):
    page = 1
    while page <= max_pages:
        # Append the current page number to the URL
        paginated_url = f"{search_page_url}&page={page}"
        print(f"Processing page {page}: {paginated_url}")
        
        # Open the LinkedIn People Search page URL
        driver.get(paginated_url)
        time.sleep(10)  # Wait for the page to load

        # Check for the stop message indicating the end of results
        try:
            # Locate the element with the message (you can modify the XPath to match the actual message element)
            stop_element = driver.find_element(By.XPATH, f"//*[contains(text(), '{stop_message}')]")
            print("Stop message found, exiting...")
            break  # Exit the loop if the stop message is found
        except:
            print(f"No stop message on page {page}, continuing...")

        # XPath to find buttons with 'to connect' in aria-label
        buttons = driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'to connect')]")

        # Print the list of buttons found
        for button in buttons:
            await send_connection_request_to_people(button)

        
        # Move to the next page
        page += 1

async def send_connection_request_to_people(button):
    button_aria_label = button.get_attribute('aria-label')
    name = button_aria_label[button_aria_label.index("Invite"):button_aria_label.index("to connect")].strip()
    print(f"Sending connection request to {name}")


driver = webdriver.Chrome()

# Call the login function
linkedin_login(linkedin_username, linkedin_password)

# Clean up the search page URL (remove &page= if it exists)
linkedin_peoples_search_page_url = parse_linkedin_peoples_search_page_url(linkedin_peoples_search_page_url)

# Connect with people, iterating over multiple pages
asyncio.run(connect_with_people(linkedin_peoples_search_page_url))

# time.sleep(60)

# Close the browser
driver.quit()