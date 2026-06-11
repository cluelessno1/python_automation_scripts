import argparse
import datetime
import os
import sys
import time

from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import InvalidSessionIdException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
PAGE_LOAD_TIMEOUT = 15   # max seconds to wait for a page to load
ELEMENT_TIMEOUT = 8      # max seconds to wait for an element to appear
CLICK_SETTLE_SECS = 0.4  # brief pause after a click for LinkedIn's JS to react
LOGIN_CHECKPOINT_TIMEOUT = 90  # max seconds to wait for manual checkpoint solve
MAX_CONNECTIONS = 10
MAX_PAGES = 10

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

VERBOSE = False
LOG_FILE = None  # opened in main() via setup_log_file()


def log(msg: str) -> None:
    print(msg)
    if LOG_FILE:
        LOG_FILE.write(msg + "\n")
        LOG_FILE.flush()


def vlog(msg: str) -> None:
    """Always written to the log file; printed to console only in --verbose mode."""
    if LOG_FILE:
        LOG_FILE.write(f"  [verbose] {msg}\n")
        LOG_FILE.flush()
    if VERBOSE:
        print(f"  [verbose] {msg}")


def setup_log_file() -> None:
    global LOG_FILE
    os.makedirs("logs", exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join("logs", f"run_{timestamp}.log")
    LOG_FILE = open(path, "w", encoding="utf-8")
    log(f"Log file: {path}")


# ---------------------------------------------------------------------------
# Browser / WebDriver helpers
# ---------------------------------------------------------------------------

def build_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    if not VERBOSE:
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
    log("Launching Chrome...")
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(5)
    return driver


def multi_tag_xpath(aria_condition: str) -> str:
    """Build an XPath matching button/div/a elements with the given aria-label condition.
    LinkedIn renders interactive elements as any of these tags depending on the UI version."""
    return f"//*[(self::button or self::div or self::a) and ({aria_condition})]"


def wait_for_page(driver, timeout=PAGE_LOAD_TIMEOUT) -> None:
    """Wait until the page's readyState is complete."""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except Exception:
        pass  # proceed anyway; page may be good enough


def wait_for_url_change(driver, from_url: str, timeout=PAGE_LOAD_TIMEOUT) -> None:
    """Wait until the URL changes away from from_url."""
    try:
        WebDriverWait(driver, timeout).until(EC.url_changes(from_url))
    except Exception:
        pass


def wait_for_element(driver_or_el, by, value, timeout=ELEMENT_TIMEOUT):
    """Wait until an element is present in DOM, return it or None."""
    try:
        return WebDriverWait(driver_or_el, timeout).until(
            EC.presence_of_element_located((by, value))
        )
    except Exception:
        return None


def find_in_shadow_dom(driver, css_selector: str):
    """Query LinkedIn's interop shadow DOM (#interop-outlet) used for modal dialogs."""
    try:
        host = driver.find_element(By.CSS_SELECTOR, "#interop-outlet")
        el = driver.execute_script("""
            const root = arguments[0].shadowRoot;
            return root ? root.querySelector(arguments[1]) : null;
        """, host, css_selector)
        if el:
            vlog(f"Found element in shadow DOM: {css_selector!r}")
        return el
    except Exception as exc:
        vlog(f"Shadow DOM query failed for {css_selector!r}: {exc}")
        return None


def wait_for_shadow_dom(driver, css_selector: str, timeout=ELEMENT_TIMEOUT):
    """Poll #interop-outlet shadow root until selector matches."""

    def _found(d):
        try:
            host = d.find_element(By.CSS_SELECTOR, "#interop-outlet")
            return d.execute_script("""
                const root = arguments[0].shadowRoot;
                return root ? root.querySelector(arguments[1]) : null;
            """, host, css_selector)
        except Exception:
            return None

    try:
        el = WebDriverWait(driver, timeout).until(_found)
        if el:
            vlog(f"Found element in shadow DOM (waited): {css_selector!r}")
        return el
    except Exception:
        vlog(f"Timed out waiting for shadow DOM: {css_selector!r}")
        return None


def ensure_modal_closed(driver) -> None:
    """Dismiss any open Connect modal before the next invite."""
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
    except Exception:
        pass

    for sel in ["[aria-label*='Dismiss']", "[aria-label*='Cancel']", "[aria-label*='Close']"]:
        el = find_in_shadow_dom(driver, sel)
        if el:
            try:
                js_click(driver, el)
                vlog("Closed modal via shadow DOM dismiss.")
            except Exception:
                pass

    def _modal_still_open(d):
        try:
            host = d.find_element(By.CSS_SELECTOR, "#interop-outlet")
            return d.execute_script("""
                const r = arguments[0].shadowRoot;
                if (!r) return false;
                return !!(r.querySelector("[aria-label*='Add a note']")
                    || r.querySelector("[aria-label*='Send invitation']"));
            """, host)
        except Exception:
            return False

    try:
        WebDriverWait(driver, ELEMENT_TIMEOUT).until(lambda d: not _modal_still_open(d))
    except Exception:
        time.sleep(CLICK_SETTLE_SECS)


def find_element_any(driver_or_el, selectors, visible_only=False):
    """Try multiple (By, value) pairs and return the first match, or None."""
    for by, value in selectors:
        try:
            elements = driver_or_el.find_elements(by, value)
            for el in elements:
                if visible_only and not el.is_displayed():
                    vlog(f"Skipping hidden element: {by}={value!r}")
                    continue
                vlog(f"Matched selector: {by}={value!r}")
                return el
            vlog(f"No match for selector: {by}={value!r}")
        except Exception as exc:
            vlog(f"Error with selector: {by}={value!r} — {exc}")
    return None


def js_click(driver, el) -> None:
    """JS click — works on any element type (div, a, button) and bypasses overlays."""
    driver.execute_script("arguments[0].click();", el)


def collect_profile_url(element) -> str | None:
    """Find the /in/ profile link from the card containing the given element."""
    for ancestor_xpath in [
        "./ancestor::li//a[contains(@href, '/in/')]",
        "./ancestor::div[.//a[contains(@href, '/in/')]][1]//a[contains(@href, '/in/')]",
        "./preceding::a[contains(@href, '/in/')][1]",
        "./following::a[contains(@href, '/in/')][1]",
    ]:
        try:
            link_el = element.find_element(By.XPATH, ancestor_xpath)
            href = link_el.get_dom_attribute("href")
            if href and "/in/" in href:
                vlog(f"Found profile link via: {ancestor_xpath}")
                return href
        except Exception:
            continue
    return None


def parse_connect_name(aria_label: str) -> str:
    if "Invite" in aria_label and "to connect" in aria_label:
        return aria_label[aria_label.index("Invite") + len("Invite"):
                      aria_label.index("to connect")].strip()
    if "Connect with" in aria_label:
        return aria_label[aria_label.index("Connect with") + len("Connect with"):].strip()
    return "Unknown"


def collect_connect_names(driver) -> list[str]:
    """Collect unique names from Connect/Invite buttons on the current search page."""
    names: list[str] = []
    xpath = multi_tag_xpath(
        "(contains(@aria-label, 'Invite') or contains(@aria-label, 'Connect')) and "
        "not(contains(@aria-label, 'Unfollow')) and "
        "not(contains(@aria-label, 'Following'))"
    )
    for el in driver.find_elements(By.XPATH, xpath):
        name = parse_connect_name(el.get_dom_attribute("aria-label") or "")
        if name != "Unknown" and name not in names:
            names.append(name)
    return names


def find_connect_element_for_name(driver, name: str):
    """Re-find a fresh Connect element for a person (avoids stale refs after modals)."""
    return find_element_any(driver, [
        (By.XPATH, multi_tag_xpath(f"contains(@aria-label, 'Invite {name}')")),
        (By.XPATH, multi_tag_xpath(f"contains(@aria-label, 'Connect with {name}')")),
    ], visible_only=True)


def find_connect_in_more_menu(driver, name: str):
    """Find Connect inside the open More dropdown — must match this person by name."""
    return find_element_any(driver, [
        (By.XPATH, f"//div[@role='menu']//a[@role='menuitem'][.//*[contains(@aria-label, 'Invite {name}')]]"),
        (By.XPATH, f"//ul[@role='menu']//a[@role='menuitem'][.//*[contains(@aria-label, 'Invite {name}')]]"),
        (By.XPATH, f"//a[@role='menuitem'][.//div[contains(@aria-label, 'Invite {name}') and contains(@aria-label, 'to connect')]]"),
        (By.XPATH, f"//div[@role='menu']//*[contains(@aria-label, 'Invite {name}') and contains(@aria-label, 'to connect')]"),
        (By.XPATH, f"//a[contains(@href, 'custom-invite')][.//*[contains(@aria-label, 'Invite {name}')]]"),
    ], visible_only=True)


def find_more_button_on_profile(driver):
    """Find the visible More button on a profile page."""
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(CLICK_SETTLE_SECS)

    more_btn = find_element_any(driver, [
        (By.XPATH, "//main//*[@aria-label='More' and (self::button or self::div)]"),
        (By.XPATH, "//*[contains(@class, 'pv-top-card')]//*[@aria-label='More' and (self::button or self::div)]"),
        (By.XPATH, "//section[contains(@class, 'artdeco-card')]//*[@aria-label='More' and (self::button or self::div)]"),
        (By.XPATH, "//*[@aria-label='More' and (self::button or self::div)]"),
        (By.XPATH, "//*[contains(@aria-label, 'More actions') and (self::button or self::div)]"),
    ], visible_only=True)

    if more_btn is None and VERBOSE:
        candidates = driver.find_elements(By.XPATH, "//*[@aria-label='More' or contains(@aria-label, 'More actions')]")
        log(f"  [verbose] More button candidates ({len(candidates)} total):")
        for el in candidates[:10]:
            log(f"    <{el.tag_name}> displayed={el.is_displayed()}")

    return more_btn

def linkedin_login(driver, username: str, password: str) -> bool:
    log("Navigating to LinkedIn login page...")
    driver.get(LINKEDIN_LOGIN_URL)
    vlog(f"Current URL: {driver.current_url}")

    try:
        # visible_only=True skips hidden passkey/Apple sign-in inputs
        username_input = find_element_any(driver, [
            (By.ID, "username"),
            (By.NAME, "session_key"),
            (By.XPATH, "//input[@type='email']"),
            (By.XPATH, "//input[contains(@placeholder, 'Email') or contains(@placeholder, 'email') or contains(@placeholder, 'phone')]"),
            (By.XPATH, "//input[@autocomplete='username']"),
        ], visible_only=True)
        if username_input is None:
            log("ERROR: Could not find a visible username/email field.")
            vlog(f"Page source snippet: {driver.page_source[:2000]}")
            return False
        username_input.click()
        username_input.send_keys(username)
        vlog("Username entered.")

        password_input = find_element_any(driver, [
            (By.ID, "password"),
            (By.NAME, "session_password"),
            (By.XPATH, "//input[@type='password']"),
        ], visible_only=True)
        if password_input is None:
            log("ERROR: Could not find password field.")
            return False
        password_input.send_keys(password)
        vlog("Password entered.")

        password_input.send_keys(Keys.RETURN)
        log("Credentials submitted. Waiting for redirect...")
        login_url = driver.current_url
        wait_for_url_change(driver, login_url, timeout=PAGE_LOAD_TIMEOUT)
        wait_for_page(driver)
        vlog(f"Post-login URL: {driver.current_url}")

        if "checkpoint" in driver.current_url or "challenge" in driver.current_url:
            log("")
            log(">>> LinkedIn is showing a security verification challenge.")
            log(">>> Please complete it in the browser window (email code, phone, etc.).")
            log(f">>> Waiting up to {LOGIN_CHECKPOINT_TIMEOUT} seconds for you to finish...")
            log("")
            try:
                WebDriverWait(driver, LOGIN_CHECKPOINT_TIMEOUT).until(
                    lambda d: "feed" in d.current_url or (
                        "checkpoint" not in d.current_url and
                        "challenge" not in d.current_url and
                        "login" not in d.current_url
                    )
                )
                vlog(f"Checkpoint resolved. URL: {driver.current_url}")
            except Exception:
                pass  # timed out; check URL below

        if "feed" in driver.current_url:
            log("Login successful.")
            return True
        elif "checkpoint" in driver.current_url or "challenge" in driver.current_url:
            log("ERROR: Security checkpoint not completed in time. Please re-run and solve it faster.")
            return False
        elif "login" in driver.current_url:
            log("ERROR: Still on login page — credentials may be wrong.")
            return False
        else:
            log(f"Login appears successful (URL: {driver.current_url}).")
            return True
    except Exception as exc:
        log(f"ERROR during login: {exc}")
        return False


def strip_page_param(url: str) -> str:
    if "&page=" in url:
        url = url.split("&page=")[0]
    vlog(f"Cleaned search URL: {url}")
    return url


def connect_with_people(driver, search_url: str, custom_message: str,
                        max_connections: int = MAX_CONNECTIONS,
                        max_pages: int = MAX_PAGES) -> None:
    search_url = strip_page_param(search_url)
    sent = 0
    sent_to: list[str] = []
    skipped: list[tuple[str, str]] = []

    for page in range(1, max_pages + 1):
        if sent >= max_connections:
            log(f"Reached max connection limit ({max_connections}). Stopping.")
            break

        paginated_url = f"{search_url}&page={page}"
        log(f"\n--- Page {page} ---")
        log(f"Opening: {paginated_url}")
        try:
            driver.get(paginated_url)
        except (InvalidSessionIdException, WebDriverException) as exc:
            log(f"Browser session lost — stopping early. ({exc.__class__.__name__})")
            break
        wait_for_page(driver)
        vlog(f"Page title: {driver.title}")

        # Scroll to trigger lazy-loading of result cards
        vlog("Scrolling to load all results...")
        for _ in range(5):
            driver.execute_script("window.scrollBy(0, 600);")
            time.sleep(0.5)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)

        # --- Direct Connect names (re-find element fresh before each click) ---
        connect_names = collect_connect_names(driver)

        # --- Profile route entries: Follow + Message buttons ---
        # Collect name + profile URL upfront to avoid stale element refs after navigation.
        profile_route_entries: list[tuple[str, str]] = []

        # Follow: <button/div aria-label="Follow {name}">
        for fb in driver.find_elements(
            By.XPATH,
            "//*[starts-with(@aria-label, 'Follow ') and (self::button or self::div)]"
        ):
            try:
                label = fb.get_dom_attribute("aria-label") or ""
                name = label[len("Follow "):].strip()
                href = collect_profile_url(fb)
                if href:
                    profile_route_entries.append((name, href))
                    vlog(f"Queued Follow profile: {name} -> {href}")
                else:
                    vlog(f"Could not find profile URL for Follow button: {name}")
            except Exception as exc:
                vlog(f"Error collecting Follow entry: {exc}")

        # Message: <a aria-label="Send a message to {name}">
        for mb in driver.find_elements(
            By.XPATH,
            "//a[starts-with(@aria-label, 'Send a message to ')]"
        ):
            try:
                label = mb.get_dom_attribute("aria-label") or ""
                name = label[len("Send a message to "):].strip()
                href = collect_profile_url(mb)
                if href:
                    profile_route_entries.append((name, href))
                    vlog(f"Queued Message profile: {name} -> {href}")
                else:
                    vlog(f"Could not find profile URL for Message button: {name}")
            except Exception as exc:
                vlog(f"Error collecting Message entry: {exc}")

        vlog(
            f"Found {len(connect_names)} Connect name(s) and "
            f"{len(profile_route_entries)} profile-route entry(ies) on page {page}."
        )

        if not connect_names and not profile_route_entries:
            log(f"No actionable buttons found on page {page}. Reached end of results or hit a rate limit.")
            if VERBOSE:
                all_els = driver.find_elements(
                    By.XPATH, "//*[@aria-label and (self::button or self::div or self::a)]"
                )
                log(f"  [verbose] All interactive elements with aria-label ({len(all_els)} total):")
                for el in all_els[:40]:
                    log(f"    <{el.tag_name}> aria-label={el.get_dom_attribute('aria-label')!r}")
            break

        # --- Process direct Connect by name (re-find element each time) ---
        for name in connect_names:
            if sent >= max_connections:
                break
            try:
                success, reason = connect_with_single_person(driver, name, custom_message)
            except Exception as exc:
                reason = str(exc)
                log(f"  SKIP {name}: {reason}")
                success = False
            if success:
                sent += 1
                sent_to.append(name)
                log(f"Progress: {sent}/{max_connections} connection requests sent.")
            elif reason:
                skipped.append((name, reason))
            ensure_modal_closed(driver)

        # --- Process Follow/Message profiles via More menu ---
        for name, profile_url in profile_route_entries:
            if sent >= max_connections:
                break
            try:
                success, reason = connect_via_profile(driver, name, profile_url, custom_message, paginated_url)
            except Exception as exc:
                reason = str(exc)
                log(f"  SKIP {name}: {reason}")
                success = False
            if success:
                sent += 1
                sent_to.append(name)
                log(f"Progress: {sent}/{max_connections} connection requests sent.")
            elif reason:
                skipped.append((name, reason))

    log(f"\nDone. Sent {sent}/{max_connections} connection requests.")
    if sent_to:
        log("Successfully connected with:")
        for name in sent_to:
            log(f"  - {name}")
    if skipped:
        log("Skipped:")
        for name, reason in skipped:
            log(f"  - {name}: {reason}")


def handle_add_note_and_send(driver, first_name: str, custom_message: str) -> tuple[bool, str | None]:
    """Handle the 'Add a note' modal. LinkedIn renders it inside #interop-outlet shadow DOM."""

    add_note_btn = wait_for_shadow_dom(driver, "[aria-label*='Add a note']")
    if add_note_btn is None:
        add_note_btn = wait_for_shadow_dom(driver, "[aria-label*='Include a note']")
    if add_note_btn is None:
        add_note_btn = find_element_any(driver, [
            (By.XPATH, multi_tag_xpath("contains(@aria-label, 'Add a note')")),
            (By.XPATH, multi_tag_xpath("contains(@aria-label, 'Include a note')")),
            (By.XPATH, "//span[contains(text(), 'Add a note')]/ancestor::*[self::button or self::div]"),
        ])

    if add_note_btn is None:
        reason = "Add a note modal did not appear"
        log(f"  SKIP {first_name}: {reason}")
        if VERBOSE:
            all_btns = driver.find_elements(
                By.XPATH, "//*[@aria-label and (self::button or self::div)]"
            )
            log(f"  [verbose] Interactive elements on page ({len(all_btns)} total):")
            for b in all_btns[:20]:
                log(f"    <{b.tag_name}> {b.get_dom_attribute('aria-label')!r}")
        ensure_modal_closed(driver)
        return False, reason

    js_click(driver, add_note_btn)
    vlog("Clicked 'Add a note'.")
    time.sleep(CLICK_SETTLE_SECS)

    success, reason = enter_custom_message(driver, first_name, custom_message)
    return success, reason


def connect_with_single_person(driver, name: str, custom_message: str) -> tuple[bool, str | None]:
    """Process a direct Connect/Invite element on the search results page."""
    first_name = name.split()[0] if name and name != "Unknown" else name
    log(f"Sending connection request to {name}...")

    ensure_modal_closed(driver)

    element = find_connect_element_for_name(driver, name)
    if element is None:
        reason = "Connect button not found on page (may already be pending)"
        log(f"  SKIP {name}: {reason}")
        return False, reason

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    time.sleep(CLICK_SETTLE_SECS)
    js_click(driver, element)
    vlog("Clicked connect element.")
    time.sleep(CLICK_SETTLE_SECS)
    wait_for_element(driver, By.CSS_SELECTOR, "#interop-outlet", timeout=ELEMENT_TIMEOUT)

    return handle_add_note_and_send(driver, first_name, custom_message)


def connect_via_profile(driver, name: str, profile_url: str,
                        custom_message: str, return_url: str) -> tuple[bool, str | None]:
    """Handle Follow/Message-only cards: navigate to profile, open More (···), click Connect."""
    first_name = name.split()[0] if name and name != "Unknown" else name
    log(f"Profile route for {name}...")

    vlog(f"Navigating to profile: {profile_url}")
    driver.get(profile_url)
    wait_for_page(driver)

    if "/in/" not in driver.current_url:
        reason = "Profile page did not load"
        log(f"  SKIP {name}: {reason}")
        driver.get(return_url)
        wait_for_page(driver)
        return False, reason

    more_btn = find_more_button_on_profile(driver)
    if more_btn is None:
        reason = "More button not visible on profile page"
        log(f"  SKIP {name}: {reason}")
        driver.get(return_url)
        wait_for_page(driver)
        return False, reason

    js_click(driver, more_btn)
    vlog("Clicked 'More' button.")
    time.sleep(CLICK_SETTLE_SECS)

    connect_option = find_connect_in_more_menu(driver, name)
    if connect_option is None:
        reason = "No Connect option in More menu (connection may be restricted)"
        log(f"  SKIP {name}: {reason}")
        if VERBOSE:
            menu_items = driver.find_elements(By.XPATH, "//a[@role='menuitem']")
            log(f"  [verbose] Open menu items ({len(menu_items)} total):")
            for item in menu_items[:10]:
                label = item.get_dom_attribute("aria-label") or item.text
                log(f"    <{item.tag_name}> {label!r} href={item.get_dom_attribute('href')!r}")
        driver.execute_script("document.body.click();")
        time.sleep(CLICK_SETTLE_SECS)
        driver.get(return_url)
        wait_for_page(driver)
        return False, reason

    vlog(f"Connect menu item: tag={connect_option.tag_name} aria-label={connect_option.get_dom_attribute('aria-label')!r}")
    js_click(driver, connect_option)
    vlog("Clicked 'Connect' from More menu.")
    time.sleep(CLICK_SETTLE_SECS)

    # Connect may open shadow modal OR navigate to custom-invite page
    wait_for_element(driver, By.CSS_SELECTOR, "#interop-outlet", timeout=ELEMENT_TIMEOUT)
    if "custom-invite" in driver.current_url or "preload" in driver.current_url:
        vlog(f"Navigated to custom-invite page: {driver.current_url}")
        wait_for_page(driver)

    success, reason = handle_add_note_and_send(driver, first_name, custom_message)

    driver.get(return_url)
    wait_for_page(driver)
    return success, reason


def enter_custom_message(driver, first_name: str, message_template: str) -> tuple[bool, str | None]:
    name = first_name
    try:
        message = message_template.format(name=first_name)
        vlog(f"Message to send: {message!r}")

        textarea = wait_for_shadow_dom(driver, "textarea#custom-message")
        if textarea is None:
            textarea = wait_for_shadow_dom(driver, "textarea")
        if textarea is None:
            textarea = find_element_any(driver, [
                (By.ID, "custom-message"),
                (By.XPATH, "//textarea"),
            ])
        if textarea is None:
            reason = "Could not find message textarea"
            log(f"  SKIP {first_name}: {reason}")
            return False, reason

        driver.execute_script("""
            arguments[0].value = '';
            arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
        """, textarea)
        textarea.send_keys(message)
        vlog("Message typed into textarea.")

        send_btn = wait_for_shadow_dom(driver, "[aria-label*='Send invitation']")
        if send_btn is None:
            send_btn = wait_for_shadow_dom(driver, "[aria-label*='Send now']")
        if send_btn is None:
            send_btn = find_element_any(driver, [
                (By.XPATH, multi_tag_xpath("contains(@aria-label, 'Send invitation')")),
                (By.XPATH, multi_tag_xpath("contains(@aria-label, 'Send now')")),
            ])
        if send_btn is None:
            reason = "Could not find Send button"
            log(f"  SKIP {first_name}: {reason}")
            return False, reason

        js_click(driver, send_btn)
        log(f"  Invitation sent to {first_name}.")

        try:
            WebDriverWait(driver, ELEMENT_TIMEOUT).until(
                lambda d: d.execute_script(
                    "const h = document.querySelector('#interop-outlet');"
                    "return !h || h.style.visibility === 'hidden' || !h.shadowRoot || !h.shadowRoot.querySelector('[aria-label*=\"Send\"]');"
                )
            )
        except Exception:
            time.sleep(CLICK_SETTLE_SECS)
        return True, None

    except Exception as exc:
        reason = str(exc)
        log(f"  ERROR while sending message to {name}: {reason}")
        return False, reason


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Send personalised LinkedIn connection requests automatically."
    )
    parser.add_argument(
        "--search-url",
        help=(
            "LinkedIn People search URL (overrides LINKEDIN_SEARCH_URL in .env). "
            "Go to LinkedIn > Search > People, apply your filters, then copy the URL."
        ),
    )
    parser.add_argument(
        "--max-connections",
        type=int,
        default=MAX_CONNECTIONS,
        help=f"Max connection requests to send per run (default: {MAX_CONNECTIONS}).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=MAX_PAGES,
        help=f"Max search result pages to iterate through (default: {MAX_PAGES}).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging to console (always written to log file).",
    )
    return parser.parse_args()


def main():
    global VERBOSE
    args = parse_args()
    VERBOSE = args.verbose

    setup_log_file()

    if VERBOSE:
        log("Verbose mode enabled.")

    username = os.getenv("LINKEDIN_USERNAME", "")
    password = os.getenv("LINKEDIN_PASSWORD", "")
    search_url = args.search_url or os.getenv("LINKEDIN_SEARCH_URL", "")
    custom_message = os.getenv("CUSTOM_MESSAGE", "Hi {name}, I'd love to connect!")

    missing = []
    if not username:
        missing.append("LINKEDIN_USERNAME")
    if not password:
        missing.append("LINKEDIN_PASSWORD")
    if not search_url:
        missing.append("LINKEDIN_SEARCH_URL (or pass --search-url)")
    if missing:
        log(f"ERROR: Missing required config: {', '.join(missing)}")
        log("Set these in your .env file or pass --search-url on the command line.")
        sys.exit(1)

    vlog(f"Username: {username}")
    vlog(f"Search URL: {search_url}")
    vlog(f"Message template: {custom_message!r}")
    vlog(f"Max connections: {args.max_connections} | Max pages: {args.max_pages}")

    driver = build_driver()
    try:
        if linkedin_login(driver, username, password):
            connect_with_people(
                driver,
                search_url,
                custom_message,
                max_connections=args.max_connections,
                max_pages=args.max_pages,
            )
    except (InvalidSessionIdException, WebDriverException) as exc:
        log(f"\nBrowser session ended unexpectedly: {exc.__class__.__name__}")
        log("The run has ended. Check the log file for what was completed.")
    finally:
        log("\nClosing browser...")
        try:
            driver.quit()
        except Exception:
            pass
        if LOG_FILE:
            LOG_FILE.close()


if __name__ == "__main__":
    main()
