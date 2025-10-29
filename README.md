# Kayako MCP Server

A Model Context Protocol (MCP) server for Kayako Classic REST API, enabling AI agents to search, filter, and analyze support tickets efficiently.

## Features

### 🔍 Search & Filter Capabilities
- **Advanced Search**: Search tickets by content, subject, staff notes, user email, or name
- **Flexible Filtering**: Filter by department, status, assigned staff, or customer
- **Smart Pagination**: Handle large result sets with offset/limit controls
- **Multiple Formats**: Output in Markdown (human-readable) or JSON (machine-readable)

### 🎯 Core Tools

1. **`kayako_search_tickets`** - Search tickets across multiple fields
2. **`kayako_get_ticket`** - Get complete ticket details with optional conversation history
3. **`kayako_list_tickets`** - List tickets with advanced filtering and sorting
4. **`kayako_get_ticket_posts`** - Retrieve full conversation history
5. **`kayako_get_departments`** - List all departments (helper for filtering)
6. **`kayako_get_ticket_statuses`** - List all ticket statuses (helper for filtering)

### 💡 Analysis-Friendly
- Clean, structured data optimized for AI analysis
- Conversation history in chronological order
- Timestamp formatting for human readability
- Content truncation with guidance for large responses
- Character limit handling (25,000 chars) with helpful messages

---

## Installation

### Prerequisites
- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) package manager (recommended) or pip
- Kayako Classic instance with REST API enabled
- Kayako API credentials (API Key and Secret Key)

### Step 1: Install dependencies

Using `uv` (recommended):
```bash
cd kayako-mcp
uv sync
```

Using `pip`:
```bash
cd kayako-mcp
pip install -e .
```

### Step 2: Configure API credentials

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` and add your Kayako credentials:
```bash
KAYAKO_API_URL=https://yourcompany.kayako.com/api/index.php
KAYAKO_API_KEY=your-api-key-here
KAYAKO_SECRET_KEY=your-secret-key-here
```

**Finding your Kayako API credentials:**
1. Log in to Kayako Admin Control Panel
2. Go to **REST API** section
3. Find your **API Key** and **Secret Key** under **API Information**
4. Copy the base API URL (usually `https://yourcompany.kayako.com/api/index.php`)

### Step 3: Test the server

```bash
# Using uv
uv run kayako_mcp.py --help

# Using python directly
python kayako_mcp.py --help
```

If configured correctly, you should see MCP server help information without errors.

---

## Usage with Claude Code

### Add to Claude Code

```bash
claude mcp add --transport stdio kayako \
  -- uv run /Users/moroz/Projects/test-skills/kayako-mcp/kayako_mcp.py
```

Or add manually to `~/.claude.json`:

```json
{
  "mcpServers": {
    "kayako": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "/Users/moroz/Projects/test-skills/kayako-mcp/kayako_mcp.py"
      ],
      "env": {
        "KAYAKO_API_URL": "https://yourcompany.kayako.com/api/index.php",
        "KAYAKO_API_KEY": "your-api-key",
        "KAYAKO_SECRET_KEY": "your-secret-key"
      }
    }
  }
}
```

### Example Queries

Once integrated with Claude Code, you can ask:

**Search queries:**
- "Search for all tickets about password reset issues"
- "Find tickets from user john@example.com"
- "Show me tickets containing 'billing error' in the last week"

**Filtering queries:**
- "List all open tickets in the Support department"
- "Show me tickets assigned to staff member #5"
- "Get all resolved tickets sorted by last activity"

**Analysis queries:**
- "Analyze the conversation history of ticket #12345"
- "What are the most common issues in open tickets?"
- "Show me full details of ticket ABC-123-456 with all replies"

**Helper queries:**
- "What departments are available?"
- "List all ticket statuses and their IDs"

---

## Tool Reference

### 1. `kayako_search_tickets`

Search for tickets by content, subject, user, or other criteria.

**Parameters:**
- `query` (string, required): Search query text
- `search_contents` (boolean): Search in ticket body (default: true)
- `search_subject` (boolean): Search in subject line (default: true)
- `search_notes` (boolean): Search in staff notes (default: false)
- `search_user_email` (boolean): Search by user email (default: false)
- `search_user_name` (boolean): Search by user name (default: false)
- `limit` (integer): Max results 1-100 (default: 20)
- `offset` (integer): Pagination offset (default: 0)
- `response_format` (string): "markdown" or "json" (default: "markdown")

**Example:**
```
Search tickets with query="password reset", search_contents=true, limit=10
```

### 2. `kayako_get_ticket`

Get complete details of a specific ticket.

**Parameters:**
- `ticket_id` (string, required): Ticket ID (display ID or internal ID)
- `include_posts` (boolean): Include conversation history (default: false)
- `response_format` (string): "markdown" or "json" (default: "markdown")

**Example:**
```
Get ticket with ticket_id="12345", include_posts=true
```

### 3. `kayako_list_tickets`

List tickets with advanced filtering.

**Parameters:**
- `department_id` (integer, optional): Filter by department
- `status_id` (integer, optional): Filter by status
- `owner_staff_id` (integer, optional): Filter by assigned staff
- `user_id` (integer, optional): Filter by customer
- `limit` (integer): Max results 1-100 (default: 20)
- `offset` (integer): Pagination offset (default: 0)
- `sort_field` (string): Sort field (default: "lastactivity")
- `sort_order` (string): "ASC" or "DESC" (default: "DESC")
- `response_format` (string): "markdown" or "json"

**Example:**
```
List tickets with status_id=1, department_id=2, limit=20, sort_order="DESC"
```

### 4. `kayako_get_ticket_posts`

Get all posts/replies in a ticket conversation.

**Parameters:**
- `ticket_id` (string, required): Ticket ID
- `response_format` (string): "markdown" or "json"

**Example:**
```
Get posts for ticket_id="12345"
```

### 5. `kayako_get_departments`

List all departments (helper for filtering).

**Parameters:**
- `response_format` (string): "markdown" or "json"

**Example:**
```
Get departments in markdown format
```

### 6. `kayako_get_ticket_statuses`

List all ticket statuses (helper for filtering).

**Parameters:**
- `response_format` (string): "markdown" or "json"

**Example:**
```
Get ticket statuses in JSON format
```

---

## Architecture

### Authentication
Uses Kayako's signature-based authentication:
1. Generate random salt for each request
2. Create signature: `Base64(SHA256(salt + secret_key))`
3. Send `apikey`, `salt`, and `signature` with each request

### XML Parsing
- Kayako Classic uses XML for all responses
- Automatic conversion to Python dictionaries
- Type inference for numbers, booleans, and strings
- Handles nested elements and attributes

### Response Formatting
- **Markdown**: Human-readable with headers, lists, timestamps
- **JSON**: Complete structured data for programmatic processing
- Character limit enforcement (25,000 chars)
- Smart truncation with guidance

### Error Handling
Clear, actionable error messages for:
- Authentication failures (401)
- Not found errors (404)
- Rate limiting (429)
- Server errors (500+)
- Network timeouts
- Invalid data formats

---

## Development

### Project Structure
```
kayako-mcp/
├── kayako_mcp.py       # Main MCP server (single file)
├── pyproject.toml      # Dependencies
├── README.md           # This file
├── .env.example        # Example environment variables
└── .env                # Your actual credentials (gitignored)
```

### Running Tests

Basic validation:
```bash
# Check Python syntax
python -m py_compile kayako_mcp.py

# Test configuration
uv run kayako_mcp.py --help
```

### Code Quality Features
- ✅ Type hints throughout
- ✅ Pydantic v2 for input validation
- ✅ Comprehensive docstrings
- ✅ DRY principle - no code duplication
- ✅ Async/await for all I/O
- ✅ MCP best practices compliance
- ✅ Tool annotations for all operations

---

## Troubleshooting

### "Authentication failed" error
- Verify `KAYAKO_API_KEY` and `KAYAKO_SECRET_KEY` are correct
- Check that API access is enabled in Kayako Admin CP
- Ensure your API key has necessary permissions

### "Request timed out" error
- Kayako server may be slow or experiencing issues
- Try again after a few moments
- Check your network connection

### "No tickets found" with valid query
- Verify the search query matches ticket content
- Try broader search terms
- Check if tickets exist in the Kayako system
- Try different search areas (contents, subject, etc.)

### "Rate limit exceeded" error
- Wait a few minutes before making more requests
- Reduce the frequency of API calls
- Consider caching results if making repeated queries

### XML parsing errors
- Contact Kayako support if this persists
- May indicate API compatibility issues
- Check Kayako version (this server is for Classic/v4)

---

## Limitations

- **Kayako Classic Only**: Designed for Kayako Classic (v3/v4), not Kayako v5+
- **Read-Only**: All tools are read-only (no ticket creation/modification yet)
- **No Attachments**: Attachment download not supported in MVP
- **XML Performance**: XML parsing is slower than JSON (inherent to Kayako Classic)
- **Rate Limits**: Subject to Kayako API rate limiting

---

## Future Enhancements

Potential additions for future versions:
- Write operations (create ticket, add reply, update status)
- Attachment support (upload/download)
- Custom field access
- Advanced analytics and reporting tools
- Bulk operations
- Time tracking data
- SLA information
- Real-time notifications

---

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request with description

---

## Support

For issues or questions:
- Open an issue on GitHub
- Check Kayako Classic API documentation: https://classichelp.kayako.com/article/45383-kayako-rest-api
- Review MCP protocol documentation: https://modelcontextprotocol.io

---

**Built with:**
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io)
- [FastMCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Pydantic v2](https://docs.pydantic.dev/)
- [httpx](https://www.python-httpx.org/)
- [lxml](https://lxml.de/)

**Created:** October 2025
**Version:** 0.1.0 (MVP)
