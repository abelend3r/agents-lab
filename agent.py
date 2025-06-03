"""
This module defines an HTML Inspection Agent and its associated tools using
the ADK (Agent Development Kit) framework.

The agent, HTMLInspectorAgent, is designed to parse and inspect HTML content,
providing users with information about its structure, such as tag counts,
element IDs, CSS class usage, and external links.

The module includes:
- Mock ADK components for local testing if ADK is not available.
- Definitions for tools that the agent can use (e.g., load_html, count_elements).
- The HTMLInspectorAgent class itself.
- A demonstration flow under `if __name__ == '__main__'` for when ADK is not present.
"""
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# --- ADK Setup ---
# Attempt to import actual ADK components.
# If ADK is not available (e.g., in a local dev environment without the full ADK setup),
# mock objects will be used to allow the agent code to run for testing purposes.
try:
    from adk.agent import Agent
    from adk.config import STORE_KEY_STATE
    from adk.tools import tool
    ADK_AVAILABLE = True
    # print("ADK components loaded.") # Keep this commented out for cleaner default output
except ImportError:
    ADK_AVAILABLE = False
    print("ADK components not found. Using mock objects for local testing.")

    # --- Mock ADK Components ---
    STORE_KEY_STATE = 'agent_data' # Using a descriptive key for the mock state

    def tool(func):
        """Mock decorator for ADK tools. Marks the function for potential discovery."""
        setattr(func, '_is_tool', True)
        return func

    class Agent:
        """Mock ADK Agent class for local testing."""
        def __init__(self, instruction: str = ""):
            self.instruction = instruction
            self.state = {STORE_KEY_STATE: {}} # Agent's application-specific data
            self._tools = {} # For storing registered mock tools
            # print("Mock Agent initialized.") # Keep this commented out for cleaner default output
            # print(f"  Instruction: {self.instruction[:100]}...")
            # print(f"  Initial agent_data: {self.state[STORE_KEY_STATE]}")


        def register_tool_fn(self, tool_func, tool_name=None):
            """Mock for registering tool functions with the agent."""
            if not tool_name:
                tool_name = tool_func.__name__
            self._tools[tool_name] = tool_func
            # print(f"Mock Agent: Registered tool '{tool_name}'") # Keep commented

        def get_tool(self, tool_name: str):
            """Helper to retrieve a registered tool for mock testing."""
            return self._tools.get(tool_name)
    # --- End Mock ADK Components ---

# --- Agent Definition ---

# AGENT_INSTRUCTION: This string provides comprehensive guidance to the LLM
# on how the HTMLInspectorAgent should behave, interact with the user,
# and utilize its available tools. It's a core part of defining the agent's persona and capabilities.
AGENT_INSTRUCTION = """Hello! I am an HTML Inspector Agent.

My main purpose is to help you understand the structure and content of HTML documents.

**How to use me:**

1.  **Load HTML:** If you haven't provided any HTML yet, I'll need it to get started. You can tell me to load HTML using the `load_html` tool. For example:
    *   "Load this HTML: `<html><body><h1>Hello</h1></body></html>`"
    *   Or simply paste the HTML content directly when prompted or if the conversation implies loading new HTML.
    *   You can also provide a `source_url` argument to `load_html` if you want me to be more accurate about what constitutes an "external" link, e.g., by invoking the tool directly: `load_html(html_string="<html>...</html>", source_url="http://example.com")`

2.  **Ask Questions:** Once HTML is loaded (I'll confirm this), you can ask me questions about it. For example:
    *   "How many `div` tags are there?"
    *   "List all element IDs."
    *   "How many elements have the class `important-text`?"
    *   "Count the external links."

3.  **Replacing HTML:** If you want to inspect a new HTML document, just load it using the `load_html` tool again. This will replace any previously loaded HTML.

**My Capabilities (Tools I can use):**
*   `load_html(html_string: str, source_url: str = None)`: Loads or replaces the HTML content I'm inspecting. It also tries to figure out the main domain of the page to identify external links correctly.
*   `count_elements(tag_name: str)`: Counts how many times a specific HTML tag (like 'div', 'p', 'a') appears.
*   `list_ids()`: Shows a list of all unique IDs found in the HTML elements.
*   `count_class_occurrences(class_name: str)`: Counts how many HTML elements use a particular CSS class.
*   `count_external_links()`: Counts how many links (<a> tags) point to websites different from the page's main domain.

If you ask a question that requires HTML to be loaded, and I don't have any, I'll remind you to provide it using `load_html`.

Let's get started! Please provide some HTML for me to inspect.
"""

# --- Helper Functions ---
def _get_html_summary(agent: Agent) -> dict:
    """
    Retrieves the parsed HTML summary from the agent's state.

    This is an internal helper function, not an LLM-invokable tool. It's used by
    other tools to access the HTML analysis results after `load_html` has run.

    Args:
        agent: The instance of the HTMLInspectorAgent.

    Returns:
        A dictionary containing the HTML summary (tag counts, IDs, etc.).

    Raises:
        ValueError: If HTML content has not been loaded or parsed yet via `load_html`.
    """
    agent_app_state = agent.state.get(STORE_KEY_STATE, {})
    if 'html_summary' not in agent_app_state or agent_app_state['html_summary'] is None:
        raise ValueError("HTML content has not been loaded or parsed yet. Please use 'load_html' first.")
    return agent_app_state['html_summary']

# --- Tool Implementations ---

@tool
def load_html(agent: Agent, html_string: str, source_url: str = None) -> str:
    """
    Loads and parses an HTML string, storing its summary in the agent's state.

    This tool should be called before any other HTML inspection tools can function.
    It attempts to infer the "home domain" of the HTML content, which is used by
    `count_external_links` for more accurate results. The home domain is inferred
    first from the `source_url` (if provided), then from `<meta property="og:url">`,
    and finally from `<link rel="canonical">` tags within the HTML.

    Args:
        agent: The instance of the HTMLInspectorAgent.
        html_string: The HTML content to be parsed, as a string.
        source_url: Optional. The URL from which the HTML was fetched.
                    This helps in determining the 'home_domain'. E.g., "http://example.com/page".

    Returns:
        A string message confirming that the HTML has been loaded and parsed.
    """
    home_domain = ""
    # Attempt to determine home_domain from source_url first
    if source_url:
        parsed_source_url = urlparse(source_url)
        if parsed_source_url.netloc: # .netloc gives the domain part
            home_domain = parsed_source_url.netloc

    # If home_domain wasn't found via source_url, try parsing the HTML for meta tags
    if not home_domain:
        temp_soup = BeautifulSoup(html_string, 'lxml') # Use lxml parser
        # Try OpenGraph URL meta tag
        og_url_tag = temp_soup.find('meta', attrs={'property': 'og:url'})
        if og_url_tag and og_url_tag.has_attr('content'):
            parsed_og_url = urlparse(og_url_tag['content'])
            if parsed_og_url.netloc:
                home_domain = parsed_og_url.netloc

        # If still no home_domain, try canonical link tag
        if not home_domain:
            canonical_tag = temp_soup.find('link', rel='canonical')
            if canonical_tag and canonical_tag.has_attr('href'):
                parsed_canonical_url = urlparse(canonical_tag['href'])
                if parsed_canonical_url.netloc:
                    home_domain = parsed_canonical_url.netloc

    # Generate the HTML summary using the determined home_domain
    summary_dict = parse_html_and_generate_summary(html_string, home_domain=home_domain)

    # Store the raw HTML, its summary, and the inferred home_domain in the agent's state
    agent.state[STORE_KEY_STATE]['raw_html'] = html_string
    agent.state[STORE_KEY_STATE]['html_summary'] = summary_dict
    agent.state[STORE_KEY_STATE]['home_domain'] = home_domain

    return "HTML loaded and parsed successfully. You can now ask questions about its structure or content."

def parse_html_and_generate_summary(html_string: str, home_domain: str = "") -> dict:
    """
    Parses an HTML string using BeautifulSoup and generates a structured summary.

    This internal helper function is called by `load_html`. It counts tag occurrences,
    extracts unique element IDs, counts CSS class occurrences, and determines the
    number of external links based on the provided `home_domain`.

    Args:
        html_string: The HTML content as a string.
        home_domain: The domain of the "home" site (e.g., "example.com"). This is
                     used to differentiate between internal and external links.
                     If empty, any link with a domain is considered external.

    Returns:
        A dictionary containing the HTML analysis:
        {
            'tag_counts': {'tag_name': count, ...},
            'ids': ['id1', 'id2', ...],
            'class_counts': {'class_name': count, ...},
            'external_link_count': count
        }
    """
    soup = BeautifulSoup(html_string, 'lxml') # Using lxml for efficient parsing
    summary = {
        'tag_counts': {},
        'ids': set(), # Use a set for initial collection to ensure uniqueness
        'class_counts': {},
        'external_link_count': 0
    }

    # Iterate over all tags in the document
    for tag in soup.find_all(True): # True matches all tags
        # Count tag occurrences
        summary['tag_counts'][tag.name] = summary['tag_counts'].get(tag.name, 0) + 1

        # Extract element IDs
        if tag.has_attr('id'):
            summary['ids'].add(tag['id'])

        # Count CSS class occurrences
        if tag.has_attr('class'):
            for class_name in tag['class']: # An element can have multiple classes (e.g., class="foo bar")
                summary['class_counts'][class_name] = summary['class_counts'].get(class_name, 0) + 1

    summary['ids'] = sorted(list(summary['ids'])) # Convert set of IDs to a sorted list

    # Count external links
    for a_tag in soup.find_all('a', href=True): # Find all <a> tags with an 'href' attribute
        href = a_tag['href']
        parsed_url = urlparse(href)

        # A link is considered for external check if it has a scheme (http, https) and a netloc (domain)
        if parsed_url.scheme and parsed_url.netloc:
            if home_domain: # If a home_domain is established
                if parsed_url.netloc != home_domain:
                    summary['external_link_count'] += 1 # External if domains differ
            else: # If no home_domain is established, any link with a domain is counted as "external"
                summary['external_link_count'] += 1
    return summary

@tool
def count_elements(agent: Agent, tag_name: str) -> int:
    """
    Counts the total number of occurrences of a specific HTML element (e.g., 'div', 'p', 'input').

    Requires HTML to be loaded first using the `load_html` tool.
    The tag name matching is case-insensitive (input 'div' will match 'DIV').

    Args:
        agent: The instance of the HTMLInspectorAgent.
        tag_name: The name of the HTML tag to count (e.g., "div", "p").

    Returns:
        The total count of the specified HTML tag. Returns 0 if the tag is not found
        or if HTML is not loaded.
    """
    summary = _get_html_summary(agent) # Ensures HTML is loaded
    return summary['tag_counts'].get(tag_name.lower(), 0) # Standardize to lowercase for matching

@tool
def list_ids(agent: Agent) -> list[str]:
    """
    Lists all unique element IDs found in the loaded HTML document.

    Requires HTML to be loaded first using the `load_html` tool.

    Args:
        agent: The instance of the HTMLInspectorAgent.

    Returns:
        A list of unique element IDs found in the HTML, sorted alphabetically.
        Returns an empty list if no IDs are found or if HTML is not loaded.
    """
    summary = _get_html_summary(agent)
    return summary['ids']

@tool
def count_class_occurrences(agent: Agent, class_name: str) -> int:
    """
    Counts how many HTML elements are associated with the given CSS class name.

    Requires HTML to be loaded first using the `load_html` tool.

    Args:
        agent: The instance of the HTMLInspectorAgent.
        class_name: The CSS class name to count (e.g., "container", "btn-primary").

    Returns:
        The total number of times the specified class name appears on elements.
        Returns 0 if the class name is not found or if HTML is not loaded.
    """
    summary = _get_html_summary(agent)
    return summary['class_counts'].get(class_name, 0)

@tool
def count_external_links(agent: Agent) -> int:
    """
    Counts the number of anchor (<a>) tags that link to an external domain.

    The determination of "external" depends on the 'home_domain' inferred during
    the `load_html` tool execution (from `source_url` or HTML meta tags).
    Requires HTML to be loaded first using the `load_html` tool.

    Args:
        agent: The instance of the HTMLInspectorAgent.

    Returns:
        The number of external links found in the HTML. Returns 0 if no external
        links are found or if HTML is not loaded.
    """
    summary = _get_html_summary(agent)
    return summary['external_link_count']

# --- Agent Class Definition ---
class HTMLInspectorAgent(Agent):
    """
    An agent specialized in parsing and inspecting HTML content.

    It uses tools to load HTML, count tags, list element IDs, count CSS class usage,
    and identify external links. The agent's behavior and interaction flow are
    guided by the `AGENT_INSTRUCTION` string provided to the underlying LLM.
    State, including the loaded HTML summary, is managed within the agent instance.
    """
    def __init__(self, instruction: str = AGENT_INSTRUCTION):
        super().__init__(instruction=instruction)
        # Ensure the dedicated application state dictionary exists and has default keys.
        # This prevents KeyErrors if tools are called before state is fully set up by load_html.
        app_state = self.state.setdefault(STORE_KEY_STATE, {})
        app_state.setdefault('html_summary', None)
        app_state.setdefault('raw_html', None)
        app_state.setdefault('home_domain', None)

        # Register all tool functions with the agent.
        # The agent will then be able to call these tools when directed by the LLM.
        self.register_tool_fn(load_html)
        self.register_tool_fn(count_elements)
        self.register_tool_fn(list_ids)
        self.register_tool_fn(count_class_occurrences)
        self.register_tool_fn(count_external_links)

# --- Main Execution / ADK Registration ---

if ADK_AVAILABLE:
    # This line makes the agent discoverable by ADK when running `adk run` or similar.
    html_inspector_agent = HTMLInspectorAgent()
else:
    # This block is for local testing and demonstration when ADK is not available.
    # It simulates a basic interaction flow with the agent, showing how tools are called
    # and how the agent's state is affected.
    print("\n--- Running Mock Agent Demonstration ---")

    # 1. Instantiate the agent
    # (The mock Agent class constructor prints initialization details if ADK_AVAILABLE is False)
    mock_agent = HTMLInspectorAgent()

    # 2. Define a sample HTML document for testing
    # This HTML includes various elements to test different aspects of the tools.
    sample_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>My Test Page</title>
        <!-- og:url is used for home_domain inference if source_url is not provided -->
        <meta property="og:url" content="http://www.mysite.com/page.html">
        <!-- canonical link can also be used for home_domain inference -->
        <link rel="canonical" href="http://www.mysite.com/canonical-page">
    </head>
    <body>
        <div id="header" class="section header-class">
            <h1>Welcome!</h1>
            <p class="intro">This is a sample HTML for testing the <strong class="name">HTML Inspector Agent</strong>.</p>
        </div>
        <div id="content" class="section content-class">
            <input type="text" id="username" class="form-input" placeholder="Username">
            <input type="password" id="password" class="form-input">
            <button id="submitBtn" class="btn btn-primary">Submit</button>
            <a href="/about">About Us (Internal relative link)</a>
            <a href="https://www.another-domain.org/contact">Contact (External link)</a>
            <a href="http://www.mysite.com/products">Products (Same Domain absolute link)</a>
            <a href="mailto:info@mysite.com">Email Us (Mailto link)</a>
        </div>
        <div id="footer" class="section footer-class">
            <p>&copy; 2024 MySite.com. All rights reserved. <span id="year">2024</span></p>
        </div>
        <script>let version = "1.0";</script> <!-- Example of a script tag -->
    </body>
    </html>
    """

    # 3. Simulate loading HTML into the agent
    print("\n--- Simulating: User provides HTML using 'load_html' tool ---")
    # In a real scenario, the LLM would decide to call this tool based on user input.
    # Providing source_url is the most reliable way to set the home_domain.
    confirmation_message = load_html(mock_agent, sample_html, source_url="http://www.mysite.com/index.html")
    print(f"Agent's response (from load_html): \"{confirmation_message}\"")
    print("Agent's internal state after loading HTML:")
    print(f"  Home Domain: {mock_agent.state[STORE_KEY_STATE].get('home_domain')}")
    # Optionally, print more detailed summary for debugging:
    # print(f"  Summary (Tag Counts): {mock_agent.state[STORE_KEY_STATE].get('html_summary', {}).get('tag_counts')}")

    # 4. Simulate asking various questions, which would trigger tool calls by the LLM
    print("\n--- Simulating: User asks questions about the loaded HTML ---")

    # Question: "How many <div> elements are there?"
    print("\nUser asks: How many <div> elements are there?")
    num_divs = count_elements(mock_agent, "div") # Note: count_elements converts tag_name to lower.
    print(f"Agent's answer (from count_elements): There are {num_divs} 'div' elements.")

    # Question: "What are the IDs of the elements on the page?"
    print("\nUser asks: What are the IDs of the elements on the page?")
    element_ids = list_ids(mock_agent)
    print(f"Agent's answer (from list_ids): The element IDs are: {element_ids}")

    # Question: "How many elements have the class 'section'?"
    print("\nUser asks: How many elements have the class 'section'?")
    num_section_class = count_class_occurrences(mock_agent, "section")
    print(f"Agent's answer (from count_class_occurrences): {num_section_class} elements have the class 'section'.")

    # Question: "How many script tags are present?" (Testing case for count_elements)
    print("\nUser asks: How many script tags are present?")
    num_script_tags = count_elements(mock_agent, "script")
    print(f"Agent's answer (from count_elements): There are {num_script_tags} 'script' elements.")

    # Question: "How many external links are there?"
    print("\nUser asks: How many external links are there?")
    num_external_links = count_external_links(mock_agent)
    print(f"Agent's answer (from count_external_links): There are {num_external_links} external links.")
    # Expected: 1 (www.another-domain.org), as www.mysite.com is home_domain.

    # 5. Simulate asking a question when HTML is not loaded
    print("\n--- Simulating: User asks a question before loading HTML (to a new agent instance) ---")
    new_mock_agent = HTMLInspectorAgent() # A fresh agent instance has no HTML loaded
    print("User asks: How many <div> elements are there?")
    try:
        # This call will trigger _get_html_summary, which should raise a ValueError.
        count_elements(new_mock_agent, "div")
    except ValueError as e:
        # In a real interaction, the LLM would receive this error from the tool call
        # and should then formulate a response to the user, like asking them to load HTML.
        print(f"Agent's internal error (as expected): \"{e}\"")
        print("Agent would typically respond to user: \"I need some HTML content first. Please use the 'load_html' tool to provide it.\"")

    print("\n--- Mock Agent Demonstration Complete ---")
