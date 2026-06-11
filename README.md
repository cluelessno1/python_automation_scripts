# python_automation_scripts
Python automation scripts helpful during job hunting.

---

## LinkedIn_custom_message_connection_request.py

Automatically sends personalised connection requests with a custom note on LinkedIn.

### Setup

**1. Install dependencies**

```bash
pip install selenium python-dotenv
```

**2. Configure your `.env` file**

Copy `.env.example` to `.env` and fill in your details:

```bash
cp .env.example .env
```

```env
LINKEDIN_USERNAME=your_email@example.com
LINKEDIN_PASSWORD=your_password

# Paste the URL from your browser after setting up People search filters on LinkedIn
LINKEDIN_SEARCH_URL=https://www.linkedin.com/search/results/people/?...

# Use {name} as a placeholder — it will be replaced with the person's first name
CUSTOM_MESSAGE=Hi {name}, I'm Jane, a software engineer exploring new opportunities. Would love to connect!
```

> `.env` is listed in `.gitignore` so your credentials are never committed.

**3. Get a fresh search URL**

1. Go to [LinkedIn People Search](https://www.linkedin.com/search/results/people/)
2. Apply the filters you want (company, title, location, etc.)
3. Copy the URL from your browser's address bar
4. Paste it into `LINKEDIN_SEARCH_URL` in `.env`

---

### Running

**Basic run (uses `.env` for everything):**

```bash
python LinkedIn_custom_message_connection_request.py
```

**Override the search URL from the command line:**

```bash
python LinkedIn_custom_message_connection_request.py --search-url "https://www.linkedin.com/search/results/people/?..."
```

**Verbose/debug mode (prints detailed logs if something breaks):**

```bash
python LinkedIn_custom_message_connection_request.py --verbose
```

**All options:**

```
--search-url URL      LinkedIn search URL (overrides .env)
--max-connections N   Max requests to send per run (default: 10)
--max-pages N         Max search pages to iterate (default: 10)
--verbose, -v         Enable verbose debug logging
```

---

### Notes

- **CAPTCHA**: There is a 15-second pause after login so you can solve a CAPTCHA if LinkedIn prompts one. You'll only see this occasionally.
- **Rate limits**: LinkedIn may warn you if you send too many connection requests in a week. Keep `--max-connections` conservative (10–20 per session is safe).
- **Python version used**: 3.13.0
