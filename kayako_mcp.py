#!/usr/bin/env python3
"""
Kayako MCP Server - Model Context Protocol server for Kayako Classic REST API.

This server provides tools to search, filter, and analyze Kayako support tickets.
Focus areas: ticket search, content extraction, and analysis support.

Environment Variables:
    KAYAKO_API_URL: Your Kayako domain API URL (e.g., https://company.kayako.com/api/index.php)
    KAYAKO_API_KEY: Your Kayako API key
    KAYAKO_SECRET_KEY: Your Kayako secret key
"""

import os
import sys
import hashlib
import base64
import secrets
import json
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

# Handle --help before importing heavy dependencies
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help', 'help']:
    print("""
Kayako MCP Server - Model Context Protocol server for Kayako Classic API

Usage:
    python kayako_mcp.py          # Start MCP server
    python kayako_mcp.py --help   # Show this help

Environment Variables (required):
    KAYAKO_API_URL     - Your Kayako API endpoint
    KAYAKO_API_KEY     - Your Kayako API key
    KAYAKO_SECRET_KEY  - Your Kayako secret key

Example .env file:
    KAYAKO_API_URL=https://company.kayako.com/api/index.php
    KAYAKO_API_KEY=your-api-key
    KAYAKO_SECRET_KEY=your-secret-key

Tools provided:
    kayako_search_tickets      - Search tickets by content/subject/user
    kayako_get_ticket          - Get complete ticket details
    kayako_list_tickets        - List tickets with filtering
    kayako_get_ticket_posts    - Get conversation history
    kayako_get_departments     - List all departments (for filtering)
    kayako_get_ticket_statuses - List all statuses (for filtering)

For integration with Claude Code:
    claude mcp add --transport stdio kayako -- uv run kayako_mcp.py
""")
    sys.exit(0)

import httpx
from lxml import etree
from pydantic import BaseModel, Field, field_validator, ConfigDict
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize MCP server
mcp = FastMCP("kayako_mcp")

# Constants
API_BASE_URL = os.getenv("KAYAKO_API_URL", "")
API_KEY = os.getenv("KAYAKO_API_KEY", "")
SECRET_KEY = os.getenv("KAYAKO_SECRET_KEY", "")
CHARACTER_LIMIT = 25000
DEFAULT_TIMEOUT = 30.0

# Validate configuration
if not API_BASE_URL or not API_KEY or not SECRET_KEY:
    print("WARNING: Kayako API credentials not configured. Please set environment variables:")
    print("  KAYAKO_API_URL, KAYAKO_API_KEY, KAYAKO_SECRET_KEY")


# ============================================================================
# Enums
# ============================================================================

class ResponseFormat(str, Enum):
    """Output format for tool responses."""
    MARKDOWN = "markdown"
    JSON = "json"


# ============================================================================
# Authentication Utilities
# ============================================================================

def _generate_signature(api_key: str, secret_key: str) -> tuple[str, str, str]:
    """Generate Kayako API authentication signature.

    Args:
        api_key: Kayako API key
        secret_key: Kayako secret key

    Returns:
        tuple: (api_key, salt, signature) ready for API request
    """
    # Generate random salt
    salt = secrets.token_hex(16)

    # Create signature: HMAC-SHA256(salt, secret_key)
    signature_bytes = hashlib.sha256(f"{salt}{secret_key}".encode()).digest()
    signature = base64.b64encode(signature_bytes).decode()

    return api_key, salt, signature


# ============================================================================
# XML Parsing Utilities
# ============================================================================

def _xml_to_dict(element: etree._Element) -> Any:
    """Convert XML element to Python dict recursively.

    Handles Kayako-specific XML structure with attributes and nested elements.

    Args:
        element: XML element to convert

    Returns:
        dict, list, or str depending on element structure
    """
    # Handle text-only elements
    if len(element) == 0:
        text = element.text
        if text is None:
            return None
        # Try to convert to appropriate type
        text = text.strip()
        if text.lower() == "true":
            return True
        if text.lower() == "false":
            return False
        if text.isdigit():
            return int(text)
        try:
            return float(text)
        except ValueError:
            return text

    # Handle elements with children
    result = {}

    # Add attributes
    if element.attrib:
        for key, value in element.attrib.items():
            result[f"@{key}"] = value

    # Add child elements
    for child in element:
        child_data = _xml_to_dict(child)
        tag = child.tag

        if tag in result:
            # Multiple elements with same tag -> convert to list
            if not isinstance(result[tag], list):
                result[tag] = [result[tag]]
            result[tag].append(child_data)
        else:
            result[tag] = child_data

    return result


def _parse_kayako_xml(xml_string: str) -> dict:
    """Parse Kayako XML response to Python dict.

    Args:
        xml_string: XML response from Kayako API

    Returns:
        dict: Parsed response data

    Raises:
        ValueError: If XML is invalid or cannot be parsed
    """
    try:
        root = etree.fromstring(xml_string.encode())
        return _xml_to_dict(root)
    except etree.XMLSyntaxError as e:
        raise ValueError(f"Invalid XML response from Kayako API: {e}")


# ============================================================================
# API Request Wrapper
# ============================================================================

async def _make_kayako_request(
    endpoint: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None
) -> dict:
    """Make authenticated request to Kayako API.

    Handles:
    - Authentication signature generation
    - XML response parsing to dict
    - Error handling
    - Timeouts

    Args:
        endpoint: API endpoint (e.g., "/Tickets/Ticket/ListAll")
        method: HTTP method (GET, POST, PUT, DELETE)
        params: URL query parameters
        data: Request body data (for POST/PUT)

    Returns:
        dict: Parsed API response

    Raises:
        httpx.HTTPStatusError: For HTTP errors
        ValueError: For XML parsing errors
    """
    # Generate authentication parameters
    api_key, salt, signature = _generate_signature(API_KEY, SECRET_KEY)

    # Build full URL
    url = f"{API_BASE_URL}{endpoint}"

    # Add authentication to parameters
    auth_params = {
        "apikey": api_key,
        "salt": salt,
        "signature": signature,
    }

    if params:
        auth_params.update(params)

    # Make request
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        response = await client.request(
            method=method,
            url=url,
            params=auth_params if method == "GET" else None,
            data=data if method in ["POST", "PUT"] else None
        )
        response.raise_for_status()

        # Parse XML response
        return _parse_kayako_xml(response.text)


# ============================================================================
# Error Handling
# ============================================================================

def _handle_kayako_error(e: Exception) -> str:
    """Provide clear, actionable error messages for all error scenarios.

    Args:
        e: Exception that occurred

    Returns:
        str: Formatted error message for the LLM
    """
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status == 401:
            return "Error: Authentication failed. Please verify your Kayako API key and secret key are correct in environment variables."
        elif status == 404:
            return "Error: Resource not found. Please verify the ticket ID or endpoint exists."
        elif status == 403:
            return "Error: Permission denied. Your API key may not have access to this resource."
        elif status == 429:
            return "Error: Rate limit exceeded. Please wait before making more requests to the Kayako API."
        elif status >= 500:
            return f"Error: Kayako server error ({status}). The server may be experiencing issues. Please try again later."
        else:
            return f"Error: HTTP {status} - {e.response.text[:200]}"

    elif isinstance(e, httpx.TimeoutException):
        return f"Error: Request timed out after {DEFAULT_TIMEOUT}s. The Kayako server may be slow or unavailable."

    elif isinstance(e, ValueError):
        return f"Error: Invalid data format - {str(e)}"

    else:
        return f"Error: Unexpected error occurred: {type(e).__name__} - {str(e)}"


# ============================================================================
# Response Formatting Utilities
# ============================================================================

def _format_timestamp(timestamp: Any) -> str:
    """Format timestamp to human-readable string.

    Args:
        timestamp: Unix timestamp or datetime string

    Returns:
        str: Formatted timestamp like "2025-10-19 14:30:00 UTC"
    """
    try:
        if isinstance(timestamp, (int, float)):
            dt = datetime.fromtimestamp(timestamp)
        elif isinstance(timestamp, str):
            dt = datetime.fromisoformat(timestamp)
        else:
            return str(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except:
        return str(timestamp)


def _truncate_text(text: str, max_length: int = 200) -> str:
    """Truncate text with ellipsis if too long.

    Args:
        text: Text to truncate
        max_length: Maximum length

    Returns:
        str: Truncated text
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def _format_ticket_markdown(ticket: dict) -> str:
    """Format a single ticket as markdown.

    Args:
        ticket: Ticket data dict

    Returns:
        str: Markdown formatted ticket
    """
    lines = []
    lines.append(f"## Ticket #{ticket.get('displayid', 'N/A')}: {ticket.get('subject', 'No Subject')}")
    lines.append("")
    lines.append(f"- **ID:** {ticket.get('id', 'N/A')}")
    lines.append(f"- **Status:** {ticket.get('status', {}).get('#text', 'Unknown') if isinstance(ticket.get('status'), dict) else ticket.get('status', 'Unknown')}")
    lines.append(f"- **Priority:** {ticket.get('priority', {}).get('#text', 'Unknown') if isinstance(ticket.get('priority'), dict) else ticket.get('priority', 'Unknown')}")
    lines.append(f"- **Department:** {ticket.get('department', {}).get('#text', 'Unknown') if isinstance(ticket.get('department'), dict) else ticket.get('department', 'Unknown')}")
    lines.append(f"- **Owner:** {ticket.get('ownerstaffname', 'Unassigned')}")
    lines.append(f"- **Creator:** {ticket.get('fullname', 'Unknown')} ({ticket.get('email', 'no-email')})")
    lines.append(f"- **Created:** {_format_timestamp(ticket.get('dateline', ''))}")
    lines.append(f"- **Last Updated:** {_format_timestamp(ticket.get('lastactivity', ''))}")

    if ticket.get('contents'):
        lines.append("")
        lines.append("**Content:**")
        lines.append(f"{_truncate_text(ticket.get('contents', ''), 500)}")

    lines.append("")
    return "\n".join(lines)


def _format_ticket_list_markdown(tickets: List[dict], total: int, offset: int, limit: int) -> str:
    """Format list of tickets as markdown with pagination.

    Args:
        tickets: List of ticket dicts
        total: Total number of tickets
        offset: Current offset
        limit: Limit per page

    Returns:
        str: Markdown formatted ticket list
    """
    lines = []
    lines.append(f"# Ticket List (showing {len(tickets)} of {total} total)")
    lines.append("")

    if offset > 0 or total > offset + len(tickets):
        lines.append(f"**Page Info:** Results {offset + 1}-{offset + len(tickets)} of {total}")
        if total > offset + len(tickets):
            lines.append(f"*Use offset={offset + limit} to see more results*")
        lines.append("")

    for ticket in tickets:
        lines.append(_format_ticket_markdown(ticket))

    return "\n".join(lines)


def _format_post_markdown(post: dict) -> str:
    """Format a single ticket post as markdown.

    Args:
        post: Post data dict

    Returns:
        str: Markdown formatted post
    """
    lines = []
    creator = post.get('fullname', 'Unknown')
    creator_type = post.get('creator', 'unknown')
    timestamp = _format_timestamp(post.get('dateline', ''))

    lines.append(f"### {creator} ({creator_type}) - {timestamp}")
    lines.append("")
    lines.append(post.get('contents', ''))
    lines.append("")
    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def _check_and_truncate(response: str, data_list: List[dict], data_type: str) -> str:
    """Check character limit and truncate with guidance if needed.

    Args:
        response: Formatted response string
        data_list: Original data list
        data_type: Type of data (for guidance message)

    Returns:
        str: Response (possibly truncated with guidance)
    """
    if len(response) <= CHARACTER_LIMIT:
        return response

    # Truncate to half the items
    truncated_count = max(1, len(data_list) // 2)
    truncation_msg = (
        f"\n\n**⚠️ RESPONSE TRUNCATED**\n"
        f"Original response was too large ({len(response)} characters > {CHARACTER_LIMIT} limit).\n"
        f"Showing {truncated_count} of {len(data_list)} {data_type}.\n\n"
        f"**To see more:**\n"
        f"- Use pagination with `offset` parameter\n"
        f"- Add more specific filters to reduce results\n"
        f"- Request smaller batches with lower `limit` value\n"
    )

    # Re-generate response with fewer items
    # This is a simplified truncation - caller should handle properly
    return response[:CHARACTER_LIMIT] + truncation_msg


# ============================================================================
# Pydantic Input Models
# ============================================================================

class TicketSearchInput(BaseModel):
    """Input model for ticket search operations."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    query: str = Field(
        ...,
        description="Search query string (e.g., 'password reset', 'billing issue', 'John Doe')",
        min_length=1,
        max_length=500
    )
    search_contents: bool = Field(
        default=True,
        description="Search in ticket contents/body"
    )
    search_subject: bool = Field(
        default=True,
        description="Search in ticket subject"
    )
    search_notes: bool = Field(
        default=False,
        description="Search in staff notes"
    )
    search_user_email: bool = Field(
        default=False,
        description="Search by user email address"
    )
    search_user_name: bool = Field(
        default=False,
        description="Search by user full name"
    )
    limit: int = Field(
        default=20,
        description="Maximum results to return",
        ge=1,
        le=100
    )
    offset: int = Field(
        default=0,
        description="Pagination offset (number of results to skip)",
        ge=0
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable"
    )

    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Query cannot be empty or whitespace only")
        return v.strip()


class GetTicketInput(BaseModel):
    """Input model for retrieving a specific ticket."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    ticket_id: str = Field(
        ...,
        description="Ticket ID - can be display ID (e.g., 'ABC-12345') or internal ID (e.g., '12345')",
        min_length=1
    )
    include_posts: bool = Field(
        default=False,
        description="Include all ticket posts/replies in the response"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable"
    )


class ListTicketsInput(BaseModel):
    """Input model for listing tickets with filters."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    department_id: Optional[int] = Field(
        default=None,
        description="Filter by department ID (use kayako_get_departments to find IDs)",
        ge=1
    )
    status_id: Optional[int] = Field(
        default=None,
        description="Filter by status ID (use kayako_get_ticket_statuses to find IDs)",
        ge=1
    )
    owner_staff_id: Optional[int] = Field(
        default=None,
        description="Filter by assigned staff member ID",
        ge=1
    )
    user_id: Optional[int] = Field(
        default=None,
        description="Filter by user/customer ID",
        ge=1
    )
    limit: int = Field(
        default=20,
        description="Maximum results to return",
        ge=1,
        le=100
    )
    offset: int = Field(
        default=0,
        description="Pagination offset",
        ge=0
    )
    sort_field: Optional[str] = Field(
        default="lastactivity",
        description="Sort field (e.g., 'lastactivity', 'lastreplier', 'dateline')"
    )
    sort_order: str = Field(
        default="DESC",
        description="Sort order: 'ASC' (oldest first) or 'DESC' (newest first)",
        pattern="^(ASC|DESC)$"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable"
    )


class GetTicketPostsInput(BaseModel):
    """Input model for retrieving ticket posts."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    ticket_id: str = Field(
        ...,
        description="Ticket ID to retrieve posts from",
        min_length=1
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable"
    )


class GetDepartmentsInput(BaseModel):
    """Input model for retrieving departments."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable"
    )


class GetTicketStatusesInput(BaseModel):
    """Input model for retrieving ticket statuses."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable"
    )


# ============================================================================
# MCP Tools
# ============================================================================

@mcp.tool(
    name="kayako_search_tickets",
    annotations={
        "title": "Search Kayako Tickets",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def kayako_search_tickets(params: TicketSearchInput) -> str:
    """Search for tickets in Kayako by content, subject, user, or other criteria.

    This tool searches across Kayako tickets using the TicketSearch API endpoint.
    You can search in multiple areas simultaneously (contents, subject, notes, email, name).

    Args:
        params (TicketSearchInput): Validated input parameters containing:
            - query (str): Search query string (e.g., "password reset", "billing")
            - search_contents (bool): Search in ticket body/contents (default: True)
            - search_subject (bool): Search in ticket subject (default: True)
            - search_notes (bool): Search in staff notes (default: False)
            - search_user_email (bool): Search by user email (default: False)
            - search_user_name (bool): Search by user name (default: False)
            - limit (int): Maximum results, 1-100 (default: 20)
            - offset (int): Pagination offset (default: 0)
            - response_format (str): 'markdown' or 'json' (default: 'markdown')

    Returns:
        str: Formatted list of matching tickets with key information.

        Markdown format includes:
        - Ticket number, subject, status, priority
        - Department, owner, creator information
        - Creation and last update timestamps
        - Content preview (truncated)
        - Pagination information if applicable

        JSON format includes complete ticket data structure.

    Examples:
        - Search for password issues: query="password reset", search_contents=True
        - Find tickets from specific user: query="john@example.com", search_user_email=True
        - Search billing tickets: query="billing", search_subject=True, search_contents=True

    Error Handling:
        - Returns "Error: Authentication failed" if API credentials are invalid
        - Returns "Error: No tickets found matching 'query'" if no results
        - Returns formatted error message for other API errors
    """
    try:
        # Build search query parameters
        search_params = {
            "query": params.query,
        }

        # Add search area flags
        search_areas = []
        if params.search_contents:
            search_areas.append("1")  # Contents
        if params.search_subject:
            search_areas.append("2")  # Subject
        if params.search_notes:
            search_areas.append("3")  # Notes
        if params.search_user_email:
            search_areas.append("4")  # User email
        if params.search_user_name:
            search_areas.append("5")  # User name

        # Kayako expects comma-separated search areas
        if search_areas:
            search_params["searchcontents"] = ",".join(search_areas)

        # Make API request
        result = await _make_kayako_request(
            endpoint="/Tickets/TicketSearch",
            method="POST",
            data=search_params
        )

        # Extract tickets from response
        tickets = result.get("ticket", [])
        if not isinstance(tickets, list):
            tickets = [tickets] if tickets else []

        # Apply offset and limit
        total = len(tickets)
        tickets = tickets[params.offset:params.offset + params.limit]

        if not tickets:
            return f"No tickets found matching query: '{params.query}'"

        # Format response
        if params.response_format == ResponseFormat.MARKDOWN:
            response = _format_ticket_list_markdown(tickets, total, params.offset, params.limit)
            return _check_and_truncate(response, tickets, "tickets")
        else:
            # JSON format
            response_data = {
                "total": total,
                "count": len(tickets),
                "offset": params.offset,
                "limit": params.limit,
                "has_more": total > params.offset + len(tickets),
                "next_offset": params.offset + params.limit if total > params.offset + len(tickets) else None,
                "tickets": tickets
            }
            return json.dumps(response_data, indent=2)

    except Exception as e:
        return _handle_kayako_error(e)


@mcp.tool(
    name="kayako_get_ticket",
    annotations={
        "title": "Get Kayako Ticket Details",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def kayako_get_ticket(params: GetTicketInput) -> str:
    """Get complete details of a specific Kayako ticket.

    Retrieves full information about a single ticket including all metadata,
    custom fields, and optionally all posts/replies in the conversation.

    Args:
        params (GetTicketInput): Validated input parameters containing:
            - ticket_id (str): Ticket ID (display ID like 'ABC-123' or internal ID)
            - include_posts (bool): Include all posts/replies (default: False)
            - response_format (str): 'markdown' or 'json' (default: 'markdown')

    Returns:
        str: Complete ticket details.

        Markdown format includes:
        - All ticket metadata (ID, status, priority, department, owner, etc.)
        - Full ticket content
        - All posts/replies if include_posts=True
        - Timestamps in human-readable format

        JSON format includes complete ticket data structure.

    Examples:
        - Get ticket basics: ticket_id="12345", include_posts=False
        - Get full conversation: ticket_id="12345", include_posts=True
        - Get by display ID: ticket_id="ABC-123-456"

    Error Handling:
        - Returns "Error: Ticket not found" if ticket ID doesn't exist
        - Returns "Error: Authentication failed" if credentials invalid
        - Returns formatted error message for other issues
    """
    try:
        # Get ticket details
        result = await _make_kayako_request(
            endpoint=f"/Tickets/Ticket/{params.ticket_id}"
        )

        ticket = result.get("ticket")
        if not ticket:
            return f"Error: Ticket {params.ticket_id} not found"

        # Get posts if requested
        posts = []
        if params.include_posts:
            try:
                posts_result = await _make_kayako_request(
                    endpoint=f"/Tickets/TicketPost/ListAll/{params.ticket_id}"
                )
                posts_data = posts_result.get("post", [])
                if not isinstance(posts_data, list):
                    posts = [posts_data] if posts_data else []
                else:
                    posts = posts_data
            except:
                # If posts fail, continue without them
                pass

        # Format response
        if params.response_format == ResponseFormat.MARKDOWN:
            lines = []
            lines.append(_format_ticket_markdown(ticket))

            if posts:
                lines.append("\n## Conversation History\n")
                for post in posts:
                    lines.append(_format_post_markdown(post))

            return "\n".join(lines)
        else:
            # JSON format
            response_data = {
                "ticket": ticket,
                "posts": posts if params.include_posts else None
            }
            return json.dumps(response_data, indent=2)

    except Exception as e:
        return _handle_kayako_error(e)


@mcp.tool(
    name="kayako_list_tickets",
    annotations={
        "title": "List Kayako Tickets with Filters",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def kayako_list_tickets(params: ListTicketsInput) -> str:
    """List tickets with advanced filtering by department, status, owner, etc.

    Retrieves a filtered list of tickets from Kayako. Supports multiple filter
    criteria and sorting options. Use helper tools (kayako_get_departments,
    kayako_get_ticket_statuses) to find valid filter IDs.

    Args:
        params (ListTicketsInput): Validated input parameters containing:
            - department_id (Optional[int]): Filter by department
            - status_id (Optional[int]): Filter by status
            - owner_staff_id (Optional[int]): Filter by assigned staff
            - user_id (Optional[int]): Filter by customer/user
            - limit (int): Maximum results, 1-100 (default: 20)
            - offset (int): Pagination offset (default: 0)
            - sort_field (str): Sort field (default: 'lastactivity')
            - sort_order (str): 'ASC' or 'DESC' (default: 'DESC')
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: Filtered list of tickets.

        Includes pagination information and filtering details.
        Markdown format shows ticket summaries.
        JSON format includes complete ticket data.

    Examples:
        - All open tickets: status_id=1
        - Tickets in support dept: department_id=2
        - My assigned tickets: owner_staff_id=5
        - Recent tickets: sort_field='lastactivity', sort_order='DESC'

    Error Handling:
        - Returns empty list if no tickets match filters
        - Returns error message for invalid filter IDs
        - Handles pagination errors gracefully
    """
    try:
        # Build endpoint with filter parameters
        endpoint_parts = ["/Tickets/Ticket/ListAll"]

        # Add filter parameters in order
        endpoint_parts.append(str(params.department_id) if params.department_id else "-1")
        endpoint_parts.append(str(params.status_id) if params.status_id else "-1")
        endpoint_parts.append(str(params.owner_staff_id) if params.owner_staff_id else "-1")
        endpoint_parts.append(str(params.user_id) if params.user_id else "-1")

        endpoint = "/".join(endpoint_parts)

        # Make API request with pagination and sorting
        api_params = {
            "count": params.limit,
            "start": params.offset,
        }

        if params.sort_field:
            api_params["sortfield"] = params.sort_field
        if params.sort_order:
            api_params["sortorder"] = params.sort_order

        result = await _make_kayako_request(
            endpoint=endpoint,
            params=api_params
        )

        # Extract tickets from response
        tickets = result.get("ticket", [])
        if not isinstance(tickets, list):
            tickets = [tickets] if tickets else []

        if not tickets:
            filter_desc = []
            if params.department_id:
                filter_desc.append(f"department_id={params.department_id}")
            if params.status_id:
                filter_desc.append(f"status_id={params.status_id}")
            if params.owner_staff_id:
                filter_desc.append(f"owner_staff_id={params.owner_staff_id}")
            if params.user_id:
                filter_desc.append(f"user_id={params.user_id}")

            filters = ", ".join(filter_desc) if filter_desc else "no filters"
            return f"No tickets found matching criteria: {filters}"

        total = len(tickets)

        # Format response
        if params.response_format == ResponseFormat.MARKDOWN:
            response = _format_ticket_list_markdown(tickets, total, params.offset, params.limit)
            return _check_and_truncate(response, tickets, "tickets")
        else:
            # JSON format
            response_data = {
                "total": total,
                "count": len(tickets),
                "offset": params.offset,
                "limit": params.limit,
                "filters": {
                    "department_id": params.department_id,
                    "status_id": params.status_id,
                    "owner_staff_id": params.owner_staff_id,
                    "user_id": params.user_id,
                },
                "has_more": total > params.offset + len(tickets),
                "next_offset": params.offset + params.limit if total > params.offset + len(tickets) else None,
                "tickets": tickets
            }
            return json.dumps(response_data, indent=2)

    except Exception as e:
        return _handle_kayako_error(e)


@mcp.tool(
    name="kayako_get_ticket_posts",
    annotations={
        "title": "Get Kayako Ticket Conversation",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def kayako_get_ticket_posts(params: GetTicketPostsInput) -> str:
    """Get all posts/replies in a ticket conversation.

    Retrieves the complete conversation history for a ticket, including all
    customer replies and staff responses in chronological order.

    Args:
        params (GetTicketPostsInput): Validated input parameters containing:
            - ticket_id (str): Ticket ID to retrieve posts from
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: Chronological list of all posts.

        Markdown format includes:
        - Author name and type (staff/user/customer)
        - Timestamp for each post
        - Full content of each post
        - Clear visual separation between posts

        JSON format includes complete post data structure.

    Examples:
        - Get conversation: ticket_id="12345"
        - Analyze support quality: ticket_id="ABC-123", response_format="json"

    Error Handling:
        - Returns "Error: Ticket not found" if ticket doesn't exist
        - Returns "No posts found" if ticket has no replies
        - Returns formatted error for other issues
    """
    try:
        # Get ticket posts
        result = await _make_kayako_request(
            endpoint=f"/Tickets/TicketPost/ListAll/{params.ticket_id}"
        )

        posts = result.get("post", [])
        if not isinstance(posts, list):
            posts = [posts] if posts else []

        if not posts:
            return f"No posts found for ticket {params.ticket_id}"

        # Format response
        if params.response_format == ResponseFormat.MARKDOWN:
            lines = []
            lines.append(f"# Ticket {params.ticket_id} - Conversation History")
            lines.append(f"\n**Total Posts:** {len(posts)}\n")
            lines.append("---\n")

            for post in posts:
                lines.append(_format_post_markdown(post))

            response = "\n".join(lines)
            return _check_and_truncate(response, posts, "posts")
        else:
            # JSON format
            response_data = {
                "ticket_id": params.ticket_id,
                "total_posts": len(posts),
                "posts": posts
            }
            return json.dumps(response_data, indent=2)

    except Exception as e:
        return _handle_kayako_error(e)


@mcp.tool(
    name="kayako_get_departments",
    annotations={
        "title": "Get Kayako Departments",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def kayako_get_departments(params: GetDepartmentsInput) -> str:
    """Get list of all departments in Kayako.

    Retrieves all departments to help with filtering tickets. Use the department
    IDs returned by this tool in kayako_list_tickets or kayako_search_tickets.

    Args:
        params (GetDepartmentsInput): Validated input parameters containing:
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: List of departments with IDs and names.

        Markdown format includes:
        - Department ID and name
        - Department type (public/private)
        - Additional metadata

        JSON format includes complete department data.

    Examples:
        - List all departments: (no special parameters needed)
        - Get IDs for filtering: response_format="json"

    Error Handling:
        - Returns error if API credentials are invalid
        - Returns "No departments found" if none exist
    """
    try:
        # Get departments
        result = await _make_kayako_request(
            endpoint="/Base/Department/ListAll"
        )

        departments = result.get("department", [])
        if not isinstance(departments, list):
            departments = [departments] if departments else []

        if not departments:
            return "No departments found"

        # Format response
        if params.response_format == ResponseFormat.MARKDOWN:
            lines = []
            lines.append("# Kayako Departments\n")

            for dept in departments:
                dept_id = dept.get("id", "N/A")
                dept_name = dept.get("title", "Unnamed Department")
                dept_type = dept.get("type", "unknown")
                lines.append(f"## {dept_name}")
                lines.append(f"- **ID:** {dept_id}")
                lines.append(f"- **Type:** {dept_type}")
                lines.append("")

            return "\n".join(lines)
        else:
            # JSON format
            response_data = {
                "total": len(departments),
                "departments": departments
            }
            return json.dumps(response_data, indent=2)

    except Exception as e:
        return _handle_kayako_error(e)


@mcp.tool(
    name="kayako_get_ticket_statuses",
    annotations={
        "title": "Get Kayako Ticket Statuses",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def kayako_get_ticket_statuses(params: GetTicketStatusesInput) -> str:
    """Get list of all ticket statuses in Kayako.

    Retrieves all ticket statuses to help with filtering. Use the status IDs
    returned by this tool in kayako_list_tickets or for understanding ticket state.

    Args:
        params (GetTicketStatusesInput): Validated input parameters containing:
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: List of ticket statuses with IDs, names, and types.

        Markdown format includes:
        - Status ID and title
        - Status type (e.g., open, closed, resolved)
        - Display order
        - Additional metadata

        JSON format includes complete status data.

    Examples:
        - List all statuses: (no special parameters needed)
        - Find "Open" status ID: response_format="markdown", look for "Open"
        - Get all status data: response_format="json"

    Error Handling:
        - Returns error if API credentials invalid
        - Returns "No statuses found" if none exist
    """
    try:
        # Get ticket statuses
        result = await _make_kayako_request(
            endpoint="/Tickets/TicketStatus/ListAll"
        )

        statuses = result.get("ticketstatus", [])
        if not isinstance(statuses, list):
            statuses = [statuses] if statuses else []

        if not statuses:
            return "No ticket statuses found"

        # Format response
        if params.response_format == ResponseFormat.MARKDOWN:
            lines = []
            lines.append("# Kayako Ticket Statuses\n")

            for status in statuses:
                status_id = status.get("id", "N/A")
                status_title = status.get("title", "Unnamed Status")
                status_type = status.get("type", "unknown")
                display_order = status.get("displayorder", "N/A")

                lines.append(f"## {status_title}")
                lines.append(f"- **ID:** {status_id}")
                lines.append(f"- **Type:** {status_type}")
                lines.append(f"- **Display Order:** {display_order}")
                lines.append("")

            return "\n".join(lines)
        else:
            # JSON format
            response_data = {
                "total": len(statuses),
                "statuses": statuses
            }
            return json.dumps(response_data, indent=2)

    except Exception as e:
        return _handle_kayako_error(e)


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    # Validate configuration before starting
    if not API_BASE_URL or not API_KEY or not SECRET_KEY:
        print("\n❌ ERROR: Kayako API credentials not configured!")
        print("\nPlease set the following environment variables:")
        print("  KAYAKO_API_URL - Your Kayako API URL (e.g., https://company.kayako.com/api/index.php)")
        print("  KAYAKO_API_KEY - Your Kayako API key")
        print("  KAYAKO_SECRET_KEY - Your Kayako secret key")
        print("\nYou can:")
        print("  1. Copy .env.example to .env and fill in your credentials")
        print("  2. Set environment variables directly")
        print("\nExiting...")
        sys.exit(1)

    # Run the MCP server
    mcp.run()
