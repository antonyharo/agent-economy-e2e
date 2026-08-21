from mcp.server import MCPServer

# Initialize MCPServer
mcp = MCPServer("test")

@mcp.tool()
def test():
    return 'test'

if __name__ == "__main__":
    mcp.run(transport="stdio")