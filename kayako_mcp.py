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
import hashlib
import base64
import secrets
import json
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

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
        
        # Type inference for common patterns
        text = text.strip()
        if text.isdigit():
            return int(text)
        if text.lower() in ('true', 'false'):
            return text.lower() == 'true'
        if '.' in text and text.replace('.', '').isdigit():
            try:
                return float(text)
            except ValueError:
                pass
        
        return text
    
    # Handle elements with children
    result = {}
    
    # Add attributes with @ prefix
    for key, value in element.attrib.items():
        result[f"@{key}"] = value
    
    # Process child elements
    children_by_tag = {}
    for child in element:
        tag = child.tag
        child_data = _xml_to_dict(child)
        
        if tag in children_by_tag:
            # Multiple children with same tag -> convert to list
            if not isinstance(children_by_tag[tag], list):
                children_by_tag[tag] = [children_by_tag[tag]]
            children_by_tag[tag].append(child_data)
        else:
            children_by_tag[tag] = child_data
    
    result.update(children_by_tag)
    
    # Add text content if present alongside children
    if element.text and element.text.strip():
        result['#text'] = element.text.strip()
    
    return result


def _parse_xml_response(xml_content: str) -> Dict[str, Any]:
    """Parse Kayako XML response into Python dict.

    Args:
        xml_content: Raw XML string from Kayako API

    Returns:
        dict: Parsed XML data

    Raises:
        ValueError: If XML parsing fails
    """
    try:
        root = etree.fromstring(xml_content.encode())
        return _xml_to_dict(root)
    except etree.XMLSyntaxError as e:
        raise ValueError(f"Invalid XML response: {e}")


# ============================================================================
# HTTP Client
# ============================================================================

async def _make_request(
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    method: str = "GET"
) -> Dict[str, Any]:
    """Make authenticated request to Kayako API.

    Args:
        endpoint: API endpoint (e.g., '/Tickets')
        params: Query parameters
        method: HTTP method

    Returns:
        dict: Parsed response data

    Raises:
        Exception: For various API errors with descriptive messages
    """
    if not API_BASE_URL or not API_KEY or not SECRET_KEY:
        raise Exception(
            "Kayako API not configured. Please set KAYAKO_API_URL, "
            "KAYAKO_API_KEY, and KAYAKO_SECRET_KEY environment variables."
        )
    
    # Generate authentication
    api_key, salt, signature = _generate_signature(API_KEY, SECRET_KEY)
    
    # Build URL
    url = f"{API_BASE_URL.rstrip('/')}{endpoint}"
    
    # Prepare parameters
    if params is None:
        params = {}
    
    # Add authentication
    params.update({
        'apikey': api_key,
        'salt': salt,
        'signature': signature
    })
    
    # Make request
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            if method == "GET":
                response = await client.get(url, params=params)
            else:
                response = await client.request(method, url, data=params)
            
            # Handle HTTP errors
            if response.status_code == 401:
                raise Exception(
                    "Authentication failed. Please check your KAYAKO_API_KEY "
                    "and KAYAKO_SECRET_KEY. Ensure API access is enabled in "
                    "Kayako Admin Control Panel."
                )
            elif response.status_code == 404:
                raise Exception(
                    "Resource not found. The ticket ID or endpoint may not exist."
                )
            elif response.status_code == 429:
                raise Exception(
                    "Rate limit exceeded. Please wait a few minutes before "
                    "making more requests."
                )
            elif response.status_code >= 500:
                raise Exception(
                    f"Kayako server error ({response.status_code}). "
                    "Please try again later or contact Kayako support."
                )
            elif response.status_code >= 400:
                raise Exception(
                    f"Request error ({response.status_code}): {response.text[:200]}"
                )
            
            response.raise_for_status()
            
        except httpx.TimeoutException:
            raise Exception(
                "Request timed out. Kayako server may be slow or experiencing "
                "issues. Please try again."
            )
        except httpx.NetworkError as e:
            raise Exception(f"Network error: {e}")
    
    # Parse XML response
    try:
        return _parse_xml_response(response.text)
    except ValueError as e:
        raise Exception(f"Failed to parse Kayako response: {e}")


# ============================================================================
# Data Models
# ============================================================================

class SearchTicketsRequest(BaseModel):
    """Request model for ticket search."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    query: str = Field(
        ...,
        description="Search query text",
        min_length=1,
        max_length=500
    )
    search_contents: bool = Field(
        default=True,
        description="Search in ticket body content"
    )
    search_subject: bool = Field(
        default=True,
        description="Search in ticket subject line"
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
        description="Search by user name"
    )
    limit: int = Field(
        default=20,
        description="Maximum number of results to return",
        ge=1,
        le=100
    )
    offset: int = Field(
        default=0,
        description="Pagination offset",
        ge=0
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Response format: markdown or json"
    )


class GetTicketRequest(BaseModel):
    """Request model for getting single ticket."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    ticket_id: str = Field(
        ...,
        description="Ticket ID (display ID or internal ID)",
        min_length=1
    )
    include_posts: bool = Field(
        default=False,
        description="Include conversation history in response"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Response format: markdown or json"
    )


class ListTicketsRequest(BaseModel):
    """Request model for listing tickets with filters."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    department_id: Optional[int] = Field(
        default=None,
        description="Filter by department ID",
        ge=1
    )
    status_id: Optional[int] = Field(
        default=None,
        description="Filter by ticket status ID",
        ge=1
    )
    owner_staff_id: Optional[int] = Field(
        default=None,
        description="Filter by assigned staff member ID",
        ge=1
    )
    user_id: Optional[int] = Field(
        default=None,
        description="Filter by customer user ID",
        ge=1
    )
    limit: int = Field(
        default=20,
        description="Maximum number of results to return",
        ge=1,
        le=100
    )
    offset: int = Field(
        default=0,
        description="Pagination offset",
        ge=0
    )
    sort_field: str = Field(
        default="lastactivity",
        description="Field to sort by"
    )
    sort_order: str = Field(
        default="DESC",
        description="Sort order: ASC or DESC"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Response format: markdown or json"
    )
    
    @field_validator('sort_order')
    @classmethod
    def validate_sort_order(cls, v: str) -> str:
        if v.upper() not in ['ASC', 'DESC']:
            raise ValueError('sort_order must be ASC or DESC')
        return v.upper()


class GetTicketPostsRequest(BaseModel):
    """Request model for getting ticket conversation."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    ticket_id: str = Field(
        ...,
        description="Ticket ID (display ID or internal ID)",
        min_length=1
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Response format: markdown or json"
    )


class GetDepartmentsRequest(BaseModel):
    """Request model for getting departments."""
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Response format: markdown or json"
    )


class GetTicketStatusesRequest(BaseModel):
    """Request model for getting ticket statuses."""
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Response format: markdown or json"
    )


# ============================================================================
# Formatting Utilities
# ============================================================================

def _format_timestamp(timestamp: Optional[str]) -> str:
    """Format timestamp for human readability.
    
    Args:
        timestamp: Unix timestamp as string or formatted datetime
        
    Returns:
        str: Human-readable timestamp
    """
    if not timestamp:
        return "Unknown"
    
    try:
        # Try parsing as Unix timestamp
        if timestamp.isdigit():
            dt = datetime.fromtimestamp(int(timestamp))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        
        # Already formatted
        return timestamp
    except (ValueError, OSError):
        return timestamp


def _truncate_content(content: str, max_length: int = CHARACTER_LIMIT) -> str:
    """Truncate content with helpful message if too long.
    
    Args:
        content: Content to potentially truncate
        max_length: Maximum allowed length
        
    Returns:
        str: Truncated content with guidance if truncated
    """
    if len(content) <= max_length:
        return content
    
    truncated = content[:max_length - 200]
    return (
        f"{truncated}\n\n"
        f"[CONTENT TRUNCATED - Original length: {len(content)} characters. "
        f"Showing first {len(truncated)} characters. "
        f"Use more specific filters or search terms to get focused results.]"
    )


def _format_ticket_markdown(ticket: Dict[str, Any], include_posts: bool = False) -> str:
    """Format ticket data as Markdown.
    
    Args:
        ticket: Ticket data from API
        include_posts: Whether to include conversation posts
        
    Returns:
        str: Formatted Markdown
    """
    # Extract basic info
    ticket_id = ticket.get('displayid', ticket.get('id', 'Unknown'))
    subject = ticket.get('subject', 'No subject')
    status_title = ticket.get('statustype', 'Unknown')
    priority_title = ticket.get('prioritytitle', 'Unknown')
    department_title = ticket.get('departmenttitle', 'Unknown')
    owner_staff_name = ticket.get('ownerstaffname', 'Unassigned')
    user_fullname = ticket.get('userfullname', 'Unknown')
    user_email = ticket.get('emailqueue', ticket.get('email', ''))
    creation_date = _format_timestamp(ticket.get('dateline'))
    last_activity = _format_timestamp(ticket.get('lastactivity'))
    
    # Build markdown
    md = f"# Ticket #{ticket_id}: {subject}\n\n"
    
    md += "## Details\n"
    md += f"- **Status:** {status_title}\n"
    md += f"- **Priority:** {priority_title}\n"
    md += f"- **Department:** {department_title}\n"
    md += f"- **Assigned to:** {owner_staff_name}\n"
    md += f"- **Customer:** {user_fullname}"
    if user_email:
        md += f" ({user_email})"
    md += "\n"
    md += f"- **Created:** {creation_date}\n"
    md += f"- **Last Activity:** {last_activity}\n\n"
    
    # Add content if available
    if 'contents' in ticket and ticket['contents']:
        md += "## Content\n"
        md += f"{ticket['contents']}\n\n"
    
    # Add posts if requested and available
    if include_posts and 'posts' in ticket:
        posts = ticket['posts']
        if isinstance(posts, dict) and 'post' in posts:
            posts_list = posts['post']
            if not isinstance(posts_list, list):
                posts_list = [posts_list]
            
            md += "## Conversation History\n\n"
            for i, post in enumerate(posts_list, 1):
                post_date = _format_timestamp(post.get('dateline'))
                creator_name = post.get('fullname', 'Unknown')
                creator_type = post.get('staffid', '') and "Staff" or "Customer"
                post_content = post.get('contents', '')
                
                md += f"### #{i} - {creator_name} ({creator_type}) - {post_date}\n\n"
                md += f"{post_content}\n\n"
    
    return _truncate_content(md)


def _format_tickets_list_markdown(tickets: List[Dict[str, Any]]) -> str:
    """Format list of tickets as Markdown.
    
    Args:
        tickets: List of ticket data from API
        
    Returns:
        str: Formatted Markdown
    """
    if not tickets:
        return "No tickets found."
    
    md = f"# Tickets ({len(tickets)} found)\n\n"
    
    for ticket in tickets:
        ticket_id = ticket.get('displayid', ticket.get('id', 'Unknown'))
        subject = ticket.get('subject', 'No subject')
        status = ticket.get('statustype', 'Unknown')
        priority = ticket.get('prioritytitle', 'Unknown')
        department = ticket.get('departmenttitle', 'Unknown')
        owner = ticket.get('ownerstaffname', 'Unassigned')
        user = ticket.get('userfullname', 'Unknown')
        last_activity = _format_timestamp(ticket.get('lastactivity'))
        
        md += f"## #{ticket_id}: {subject}\n"
        md += f"- **Status:** {status} | **Priority:** {priority} | **Dept:** {department}\n"
        md += f"- **Assigned:** {owner} | **Customer:** {user}\n"
        md += f"- **Last Activity:** {last_activity}\n\n"
    
    return _truncate_content(md)


def _format_posts_markdown(posts: List[Dict[str, Any]], ticket_id: str) -> str:
    """Format ticket posts as Markdown.
    
    Args:
        posts: List of post data from API
        ticket_id: Ticket identifier
        
    Returns:
        str: Formatted Markdown
    """
    if not posts:
        return f"No posts found for ticket #{ticket_id}."
    
    md = f"# Conversation History - Ticket #{ticket_id}\n\n"
    
    for i, post in enumerate(posts, 1):
        post_date = _format_timestamp(post.get('dateline'))
        creator_name = post.get('fullname', 'Unknown')
        creator_type = "Staff" if post.get('staffid') else "Customer"
        post_content = post.get('contents', '')
        
        md += f"## #{i} - {creator_name} ({creator_type})\n"
        md += f"**Date:** {post_date}\n\n"
        md += f"{post_content}\n\n"
        md += "---\n\n"
    
    return _truncate_content(md)


def _format_departments_markdown(departments: List[Dict[str, Any]]) -> str:
    """Format departments as Markdown.
    
    Args:
        departments: List of department data from API
        
    Returns:
        str: Formatted Markdown
    """
    if not departments:
        return "No departments found."
    
    md = f"# Departments ({len(departments)} found)\n\n"
    
    for dept in departments:
        dept_id = dept.get('id', 'Unknown')
        title = dept.get('title', 'No title')
        module = dept.get('module', 'Unknown')
        parent_id = dept.get('parentdepartmentid', '')
        
        md += f"## {title}\n"
        md += f"- **ID:** {dept_id}\n"
        md += f"- **Module:** {module}\n"
        if parent_id:
            md += f"- **Parent ID:** {parent_id}\n"
        md += "\n"
    
    return md


def _format_statuses_markdown(statuses: List[Dict[str, Any]]) -> str:
    """Format ticket statuses as Markdown.
    
    Args:
        statuses: List of status data from API
        
    Returns:
        str: Formatted Markdown
    """
    if not statuses:
        return "No ticket statuses found."
    
    md = f"# Ticket Statuses ({len(statuses)} found)\n\n"
    
    for status in statuses:
        status_id = status.get('id', 'Unknown')
        title = status.get('title', 'No title')
        status_type = status.get('type', 'Unknown')
        department_id = status.get('departmentid', '')
        
        md += f"## {title}\n"
        md += f"- **ID:** {status_id}\n"
        md += f"- **Type:** {status_type}\n"
        if department_id:
            md += f"- **Department ID:** {department_id}\n"
        md += "\n"
    
    return md


# ============================================================================
# Tool Implementations
# ============================================================================

@mcp.tool()
async def kayako_search_tickets(request: SearchTicketsRequest) -> str:
    """Search for tickets by content, subject, user, or other criteria.
    
    This tool searches across ticket fields based on the specified criteria.
    Use different search_* parameters to target specific fields.
    
    Args:
        request: Search parameters including query and search options
        
    Returns:
        str: Formatted search results (Markdown or JSON)
        
    Examples:
        - Search for "password reset" in ticket contents and subjects
        - Find tickets from user "john@example.com" 
        - Search staff notes for "billing issue"
    """
    # Build search parameters
    params = {
        'e': '/Tickets/TicketSearch',
        'query': request.query,
        'limit': request.limit,
        'start': request.offset
    }
    
    # Add search field flags
    search_fields = []
    if request.search_contents:
        search_fields.append('contents')
    if request.search_subject:
        search_fields.append('subject')
    if request.search_notes:
        search_fields.append('notes')
    if request.search_user_email:
        search_fields.append('usergroup')
    if request.search_user_name:
        search_fields.append('user')
    
    if search_fields:
        params['searchtype'] = ','.join(search_fields)
    
    # Make API request
    try:
        response = await _make_request('/Tickets/TicketSearch', params, 'POST')
    except Exception as e:
        return f"Error searching tickets: {e}"
    
    # Parse response
    if 'ticket' not in response:
        return "No tickets found matching your search criteria."
    
    tickets_data = response['ticket']
    if not isinstance(tickets_data, list):
        tickets_data = [tickets_data]
    
    # Format response
    if request.response_format == ResponseFormat.JSON:
        return json.dumps(tickets_data, indent=2)
    else:
        return _format_tickets_list_markdown(tickets_data)


@mcp.tool()
async def kayako_get_ticket(request: GetTicketRequest) -> str:
    """Get complete details of a specific ticket.
    
    Retrieves full ticket information including metadata, content, and 
    optionally the conversation history.
    
    Args:
        request: Ticket request with ID and options
        
    Returns:
        str: Formatted ticket details (Markdown or JSON)
        
    Examples:
        - Get ticket #12345 without conversation history
        - Get ticket ABC-456 with full conversation posts
    """
    # Get ticket details
    try:
        endpoint = f'/Tickets/Ticket/{request.ticket_id}'
        response = await _make_request(endpoint)
    except Exception as e:
        return f"Error getting ticket: {e}"
    
    # Parse ticket data
    if 'ticket' not in response:
        return f"Ticket #{request.ticket_id} not found."
    
    ticket_data = response['ticket']
    if isinstance(ticket_data, list):
        ticket_data = ticket_data[0]
    
    # Get posts if requested
    if request.include_posts:
        try:
            posts_endpoint = f'/Tickets/TicketPost/ListAll/{request.ticket_id}'
            posts_response = await _make_request(posts_endpoint)
            
            if 'post' in posts_response:
                posts_data = posts_response['post']
                if not isinstance(posts_data, list):
                    posts_data = [posts_data]
                ticket_data['posts'] = {'post': posts_data}
        except Exception:
            # Continue without posts if they can't be fetched
            pass
    
    # Format response
    if request.response_format == ResponseFormat.JSON:
        return json.dumps(ticket_data, indent=2)
    else:
        return _format_ticket_markdown(ticket_data, request.include_posts)


@mcp.tool()
async def kayako_list_tickets(request: ListTicketsRequest) -> str:
    """List tickets with advanced filtering and sorting.
    
    Retrieve tickets based on department, status, assigned staff, or customer.
    Supports pagination and sorting options.
    
    Args:
        request: Filtering and pagination parameters
        
    Returns:
        str: Formatted ticket list (Markdown or JSON)
        
    Examples:
        - List all open tickets in department 2
        - Get tickets assigned to staff member #5
        - Show resolved tickets sorted by creation date
    """
    # Build filter parameters
    params = {
        'limit': request.limit,
        'start': request.offset,
        'sortfield': request.sort_field,
        'sortorder': request.sort_order
    }
    
    # Add filters
    if request.department_id is not None:
        params['departmentid'] = request.department_id
    if request.status_id is not None:
        params['statusid'] = request.status_id
    if request.owner_staff_id is not None:
        params['ownerstaffid'] = request.owner_staff_id
    if request.user_id is not None:
        params['userid'] = request.user_id
    
    # Make API request
    try:
        response = await _make_request('/Tickets/Ticket', params)
    except Exception as e:
        return f"Error listing tickets: {e}"
    
    # Parse response
    if 'ticket' not in response:
        return "No tickets found matching the specified criteria."
    
    tickets_data = response['ticket']
    if not isinstance(tickets_data, list):
        tickets_data = [tickets_data]
    
    # Format response
    if request.response_format == ResponseFormat.JSON:
        return json.dumps(tickets_data, indent=2)
    else:
        return _format_tickets_list_markdown(tickets_data)


@mcp.tool()
async def kayako_get_ticket_posts(request: GetTicketPostsRequest) -> str:
    """Get all posts/replies in a ticket conversation.
    
    Retrieves the complete conversation history for a ticket in chronological order.
    Includes both customer and staff responses.
    
    Args:
        request: Ticket ID and formatting options
        
    Returns:
        str: Formatted conversation history (Markdown or JSON)
        
    Examples:
        - Get conversation history for ticket #12345
        - Analyze all replies in ticket ABC-456
    """
    # Get posts
    try:
        endpoint = f'/Tickets/TicketPost/ListAll/{request.ticket_id}'
        response = await _make_request(endpoint)
    except Exception as e:
        return f"Error getting ticket posts: {e}"
    
    # Parse response
    if 'post' not in response:
        return f"No posts found for ticket #{request.ticket_id}."
    
    posts_data = response['post']
    if not isinstance(posts_data, list):
        posts_data = [posts_data]
    
    # Format response
    if request.response_format == ResponseFormat.JSON:
        return json.dumps(posts_data, indent=2)
    else:
        return _format_posts_markdown(posts_data, request.ticket_id)


@mcp.tool()
async def kayako_get_departments(request: GetDepartmentsRequest) -> str:
    """List all departments (helper for filtering).
    
    Retrieves all available departments with their IDs and titles.
    Use department IDs for filtering tickets by department.
    
    Args:
        request: Response formatting options
        
    Returns:
        str: Formatted department list (Markdown or JSON)
        
    Examples:
        - Get all departments to see available filter options
        - Find department ID for "Technical Support"
    """
    # Get departments
    try:
        response = await _make_request('/Base/Department')
    except Exception as e:
        return f"Error getting departments: {e}"
    
    # Parse response
    if 'department' not in response:
        return "No departments found."
    
    departments_data = response['department']
    if not isinstance(departments_data, list):
        departments_data = [departments_data]
    
    # Format response
    if request.response_format == ResponseFormat.JSON:
        return json.dumps(departments_data, indent=2)
    else:
        return _format_departments_markdown(departments_data)


@mcp.tool()
async def kayako_get_ticket_statuses(request: GetTicketStatusesRequest) -> str:
    """List all ticket statuses (helper for filtering).
    
    Retrieves all available ticket statuses with their IDs and titles.
    Use status IDs for filtering tickets by status.
    
    Args:
        request: Response formatting options
        
    Returns:
        str: Formatted status list (Markdown or JSON)
        
    Examples:
        - Get all ticket statuses to see filtering options
        - Find status ID for "Open" or "Resolved" tickets
    """
    # Get ticket statuses
    try:
        response = await _make_request('/Tickets/TicketStatus')
    except Exception as e:
        return f"Error getting ticket statuses: {e}"
    
    # Parse response
    if 'ticketstatus' not in response:
        return "No ticket statuses found."
    
    statuses_data = response['ticketstatus']
    if not isinstance(statuses_data, list):
        statuses_data = [statuses_data]
    
    # Format response
    if request.response_format == ResponseFormat.JSON:
        return json.dumps(statuses_data, indent=2)
    else:
        return _format_statuses_markdown(statuses_data)


# ============================================================================
# Server Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    import sys
    
    # Handle command line arguments
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help', 'help']:
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
    kayako_search_tickets     - Search tickets by content/subject/user
    kayako_get_ticket         - Get complete ticket details
    kayako_list_tickets       - List tickets with filtering
    kayako_get_ticket_posts   - Get conversation history
    kayako_get_departments    - List all departments (for filtering)
    kayako_get_ticket_statuses - List all statuses (for filtering)

For integration with Claude Code:
    claude mcp add --transport stdio kayako -- uv run kayako_mcp.py

""")
        sys.exit(0)
    
    # Run the MCP server
    mcp.run()
