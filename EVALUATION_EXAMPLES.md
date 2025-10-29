# Kayako MCP Server - Evaluation Examples

This document contains example queries and scenarios for testing the Kayako MCP server with Claude Code or other MCP clients.

---

## Prerequisites

Before running these examples, ensure:
1. Kayako MCP server is installed and configured
2. `.env` file contains valid Kayako API credentials
3. Server is added to Claude Code configuration
4. You have actual tickets in your Kayako instance

---

## Basic Discovery Queries

### 1. Explore Available Departments

**Query:**
```
What departments are available in our Kayako instance?
```

**Expected behavior:**
- Tool: `kayako_get_departments`
- Returns list of all departments with IDs and names
- Useful for understanding ticket organization

### 2. Explore Ticket Statuses

**Query:**
```
List all ticket statuses in Kayako and show me their IDs
```

**Expected behavior:**
- Tool: `kayako_get_ticket_statuses`
- Returns all status types (Open, Closed, Resolved, etc.)
- Provides IDs needed for filtering

---

## Search Scenarios

### 3. Content Search

**Query:**
```
Search for tickets about password reset issues
```

**Expected behavior:**
- Tool: `kayako_search_tickets`
- Parameters: `query="password reset"`, `search_contents=true`, `search_subject=true`
- Returns matching tickets with previews

### 4. User-Specific Search

**Query:**
```
Find all tickets from john@example.com
```

**Expected behavior:**
- Tool: `kayako_search_tickets`
- Parameters: `query="john@example.com"`, `search_user_email=true`
- Returns tickets created by that user

### 5. Staff Notes Search

**Query:**
```
Search internal staff notes for "urgent escalation"
```

**Expected behavior:**
- Tool: `kayako_search_tickets`
- Parameters: `query="urgent escalation"`, `search_notes=true`
- Returns tickets with matching internal notes

---

## Filtering Scenarios

### 6. Department Filter

**Query:**
```
Show me all open tickets in the Support department
```

**Expected behavior:**
1. Tool: `kayako_get_departments` - to find Support department ID
2. Tool: `kayako_get_ticket_statuses` - to find Open status ID
3. Tool: `kayako_list_tickets` with filters
- Parameters: `department_id=X`, `status_id=Y`

### 7. Assigned Tickets

**Query:**
```
List all tickets assigned to staff member ID 5, sorted by most recent first
```

**Expected behavior:**
- Tool: `kayako_list_tickets`
- Parameters: `owner_staff_id=5`, `sort_field="lastactivity"`, `sort_order="DESC"`

### 8. Customer Tickets

**Query:**
```
Get all tickets for customer ID 123
```

**Expected behavior:**
- Tool: `kayako_list_tickets`
- Parameters: `user_id=123`
- Returns all tickets from that customer

---

## Detailed Retrieval Scenarios

### 9. Single Ticket Details

**Query:**
```
Get full details of ticket #12345
```

**Expected behavior:**
- Tool: `kayako_get_ticket`
- Parameters: `ticket_id="12345"`, `include_posts=false`
- Returns complete ticket information

### 10. Ticket with Conversation

**Query:**
```
Show me ticket ABC-123-456 with the complete conversation history
```

**Expected behavior:**
- Tool: `kayako_get_ticket`
- Parameters: `ticket_id="ABC-123-456"`, `include_posts=true`
- Returns ticket + all posts chronologically

### 11. Conversation Analysis

**Query:**
```
Get the conversation history for ticket 12345 to analyze response times
```

**Expected behavior:**
- Tool: `kayako_get_ticket_posts`
- Parameters: `ticket_id="12345"`
- Returns all posts with timestamps

---

## Pagination Scenarios

### 12. Large Result Set

**Query:**
```
List the first 10 tickets, then show me the next 10
```

**Expected behavior:**
1. Tool: `kayako_list_tickets` with `limit=10`, `offset=0`
2. Tool: `kayako_list_tickets` with `limit=10`, `offset=10`
- Demonstrates pagination

### 13. Filtered Pagination

**Query:**
```
Search for "billing" tickets, show first 5 results
```

**Expected behavior:**
- Tool: `kayako_search_tickets`
- Parameters: `query="billing"`, `limit=5`, `offset=0`
- Returns first 5 matching tickets

---

## Complex Analysis Scenarios

### 14. Department Workload Analysis

**Query:**
```
Analyze the ticket volume across all departments
```

**Expected behavior:**
1. Tool: `kayako_get_departments` - get all departments
2. Multiple `kayako_list_tickets` calls - one per department
3. Aggregates and compares volumes

### 15. Status Distribution

**Query:**
```
How many tickets are in each status?
```

**Expected behavior:**
1. Tool: `kayako_get_ticket_statuses` - get all statuses
2. Multiple `kayako_list_tickets` calls - one per status
3. Counts and presents distribution

### 16. Recent Activity Review

**Query:**
```
What are the 20 most recently updated tickets?
```

**Expected behavior:**
- Tool: `kayako_list_tickets`
- Parameters: `limit=20`, `sort_field="lastactivity"`, `sort_order="DESC"`

---

## Multi-Tool Workflow Scenarios

### 17. Topic Analysis Workflow

**Query:**
```
Find all password reset tickets and analyze the common issues mentioned
```

**Expected behavior:**
1. Tool: `kayako_search_tickets` - find password tickets
2. Tool: `kayako_get_ticket` - get details for each
3. AI analyzes content for patterns

### 18. Support Quality Check

**Query:**
```
Get the 5 most recent resolved tickets and check average response time
```

**Expected behavior:**
1. Tool: `kayako_get_ticket_statuses` - find "Resolved" status ID
2. Tool: `kayako_list_tickets` - filter by resolved status
3. Tool: `kayako_get_ticket_posts` - get conversation for each
4. AI calculates time between posts

### 19. Customer Journey Mapping

**Query:**
```
Show me all interactions with customer email support@example.com
```

**Expected behavior:**
1. Tool: `kayako_search_tickets` - search by email
2. Tool: `kayako_get_ticket_posts` - get conversations
3. AI builds timeline of interactions

---

## Edge Cases and Error Handling

### 20. Non-Existent Ticket

**Query:**
```
Get details of ticket 99999999
```

**Expected behavior:**
- Tool: `kayako_get_ticket`
- Returns: "Error: Ticket not found" with guidance

### 21. Empty Search Results

**Query:**
```
Search for tickets about "xyz123nonexistent"
```

**Expected behavior:**
- Tool: `kayako_search_tickets`
- Returns: "No tickets found matching query: 'xyz123nonexistent'"

### 22. Invalid Filter Combination

**Query:**
```
List tickets with department_id=999999
```

**Expected behavior:**
- Tool: `kayako_list_tickets`
- Returns: "No tickets found matching criteria" or empty list

---

## Format Testing

### 23. JSON Output

**Query:**
```
Get departments in JSON format for programmatic processing
```

**Expected behavior:**
- Tool: `kayako_get_departments`
- Parameters: `response_format="json"`
- Returns structured JSON data

### 24. Markdown Output

**Query:**
```
Show me ticket 12345 in a readable format
```

**Expected behavior:**
- Tool: `kayako_get_ticket`
- Parameters: `response_format="markdown"` (default)
- Returns formatted markdown

---

## Performance Testing

### 25. Large Batch Retrieval

**Query:**
```
Get the last 100 tickets
```

**Expected behavior:**
- Tool: `kayako_list_tickets`
- Parameters: `limit=100`, `sort_order="DESC"`
- May trigger character limit truncation with guidance

### 26. Character Limit Handling

**Query:**
```
Search for common term that matches many tickets
```

**Expected behavior:**
- Tool: `kayako_search_tickets`
- If results > 25,000 chars, should truncate with helpful message

---

## Real-World Use Cases

### 27. Morning Triage

**Query:**
```
What tickets were updated in the last 24 hours? Show me the open ones first
```

**Expected behavior:**
- Tool: `kayako_list_tickets`
- Filters and sorts appropriately

### 28. Escalation Review

**Query:**
```
Find tickets with "escalation" or "urgent" in staff notes
```

**Expected behavior:**
- Tool: `kayako_search_tickets`
- Parameters: `query="escalation urgent"`, `search_notes=true`

### 29. Knowledge Base Candidate

**Query:**
```
Search for tickets about "how to change password" to create KB article
```

**Expected behavior:**
1. Tool: `kayako_search_tickets` - find related tickets
2. Tool: `kayako_get_ticket_posts` - get solutions
3. AI synthesizes common solutions

### 30. Customer Satisfaction Analysis

**Query:**
```
Get all resolved tickets from last week and analyze resolution quality
```

**Expected behavior:**
1. Tool: `kayako_list_tickets` - filter resolved
2. Tool: `kayako_get_ticket_posts` - get conversations
3. AI analyzes for satisfaction indicators

---

## Testing Checklist

When evaluating the Kayako MCP server, verify:

- [ ] All 6 tools are discoverable and callable
- [ ] Authentication works correctly
- [ ] Search returns relevant results
- [ ] Filtering by department works
- [ ] Filtering by status works
- [ ] Pagination works (offset/limit)
- [ ] Both JSON and Markdown formats work
- [ ] Error messages are clear and actionable
- [ ] Character limits are enforced
- [ ] Truncation messages provide guidance
- [ ] Timestamps are human-readable
- [ ] Ticket IDs work (both display and internal)
- [ ] Empty results handled gracefully
- [ ] XML parsing works for all responses

---

## Notes for Evaluators

### What to Test
1. **Basic functionality** - Each tool works independently
2. **Multi-tool workflows** - Tools work together for complex queries
3. **Error handling** - Graceful failure modes
4. **Performance** - Response times and character limits
5. **Usability** - Clear outputs and helpful guidance

### Expected Limitations
- Read-only operations (no write/update)
- XML parsing performance (inherent to Kayako Classic)
- Rate limiting (enforced by Kayako API)
- Attachment access not supported

### Success Criteria
- AI can successfully search and filter tickets
- AI can retrieve complete ticket information
- AI can analyze conversation history
- AI can navigate complex multi-step workflows
- Error messages guide AI to correct usage

---

**Evaluation Version:** 0.1.0
**Last Updated:** October 2025
