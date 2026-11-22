import os
import sys
import json
import logging
from pathlib import Path
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
from pydantic import AnyUrl
from typing import Any, Dict, List
import sys

sys.dont_write_bytecode = True

# Use absolute imports

from nlp_processor import NLPProcessor

from cad_controller import CADController


# Configure UTF-8 encoding for Windows
if sys.platform == "win32" and os.environ.get('PYTHONIOENCODING') is None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('cad_mcp.log', encoding='utf-8')
    ]
)


logger = logging.getLogger('mcp_cad_server')
logger.info("Starting the CAD MCP server")


PROMPT_TEMPLATE = """
This assistant demonstrates how to use the CAD MCP service. You can control CAD software directly from the conversation to create and modify drawings.

<cad-mcp>

Prompt:
This server provides a preset prompt named "cad-assistant" to help users control CAD with natural language instructions. Users can ask it to draw shapes, modify drawing elements, or save a drawing.

Resource:
This server provides the "drawing://current" resource, which represents the state of the current CAD drawing.

Tools:

This server provides the following basic drawing tools:
"draw_line": Draw a line in CAD
"draw_circle": Draw a circle in CAD
"draw_arc": Draw an arc in CAD
"draw_ellipse": Draw an ellipse in CAD
"draw_polyline": Draw a polyline in CAD
"draw_rectangle": Draw a rectangle in CAD
"draw_text": Add text in CAD
"draw_hatch": Draw a hatch in CAD
"save_drawing": Save the current drawing
"add_dimension": Add a linear dimension in CAD
"process_command": Process a natural language command and convert it to a CAD operation

</cad-mcp>

Start the demonstration in a friendly way, for example: "Hi! Today I will show you how to use the CAD MCP service. You can control CAD software directly from our conversation to create and modify drawings without operating the interface manually. Let us get started!"
"""

# To be implemented later
# "erase_entity": Delete the specified entity
# "move_entity": Move the specified entity
# "rotate_entity": Rotate the specified entity
# "scale_entity": Scale the specified entity

class Config:

    def __init__(self):
        # Read config.json directly
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        logger.info("Configuration file loaded successfully")

    @property
    def server_name(self) -> str:
        return self.config['server']['name']

    @property
    def server_version(self) -> str:
        return self.config['server']['version']

class CADService:
    def __init__(self):
        """Initialize the CAD service"""
        self.controller = CADController()
        self.nlp_processor = NLPProcessor()
        self.drawing_state = {
            "entities": [],
            "current_layer": "0",
            "last_command": "",
            "last_result": ""
        }
        logger.info("CAD service initialized")
    
    def start_cad(self):
        """Start CAD"""
        return self.controller.start_cad()

    ############################################ addition

    def rename_all_blocks(self, prefix: str = "Pen") -> List[str]:
        """Rename all user-defined blocks in the drawing to Pen-1, Pen-2, ..."""
        if not self.controller.is_running():
            self.start_cad()

        renamed = []
        index = 1
        for block in self.controller.doc.Blocks:
            name = block.Name
            if name.startswith("*"):  # Skip system blocks like *Model_Space
                continue
            new_name = f"{prefix}-{index}"
            if name.lower() != new_name.lower():
                success = self.controller.rename_block(name, new_name)
                if success:
                    renamed.append((name, new_name))
                    index += 1
        return renamed


    def rename_block(self, old_name: str, new_name: str):
        """Rename a block definition from old_name to new_name"""
        if not self.controller.is_running():
            self.start_cad()

        success = self.controller.rename_block(old_name, new_name)
        self.drawing_state["last_command"] = f"Rename block '{old_name}' to '{new_name}'"
        self.drawing_state["last_result"] = "Success" if success else "Failed"
        return success

    ############################################

    def draw_line(self, start_point, end_point, layer=None, color=None, lineweight=None):
        """Draw a line"""
        if not self.controller.is_running():
            self.start_cad()
        
        # Use the current layer or the specified layer
        current_layer = layer or self.drawing_state["current_layer"]
        
        result = self.controller.draw_line(start_point, end_point, current_layer, color, lineweight)
        if result:
            self.drawing_state["entities"].append({
                "type": "line",
                "start": start_point,
                "end": end_point,
                "layer": current_layer,
                "color": color,
                "lineweight": lineweight
            })
            self.drawing_state["last_command"] = f"Draw line from {start_point} to {end_point}"
            self.drawing_state["last_result"] = "Success"
        else:
            self.drawing_state["last_result"] = "Failed"
        
        return result
    
    def draw_circle(self, center, radius, layer=None, color=None, lineweight=None):
        """Draw a circle"""
        if not self.controller.is_running():
            self.start_cad()
        
        # Use the current layer or the specified layer
        current_layer = layer or self.drawing_state["current_layer"]
        
        result = self.controller.draw_circle(center, radius, current_layer, color, lineweight)
        if result:
            self.drawing_state["entities"].append({
                "type": "circle",
                "center": center,
                "radius": radius,
                "layer": current_layer,
                "color": color,
                "lineweight": lineweight
            })
            self.drawing_state["last_command"] = f"Draw circle: center={center}; radius={radius}; layer={current_layer}"
            self.drawing_state["last_result"] = "Success"
        else:
            self.drawing_state["last_result"] = "Failed"
        
        return result
    
    def draw_arc(self, center, radius, start_angle, end_angle, layer=None, color=None, lineweight=None):
        """Draw an arc"""
        if not self.controller.is_running():
            self.start_cad()
        
        # Use the current layer or the specified layer
        current_layer = layer or self.drawing_state["current_layer"]
        
        result = self.controller.draw_arc(center, radius, start_angle, end_angle, current_layer, color, lineweight)

        if result:
            self.drawing_state["entities"].append({
                "type": "arc",
                "center": center,
                "radius": radius,
                "start_angle": start_angle,
                "end_angle": end_angle,
                "layer": current_layer,
                "color": color,
                "lineweight": lineweight
            })
            self.drawing_state["last_command"] = f"Draw arc: center={center}; radius={radius}; start angle={start_angle}; end angle={end_angle}; layer={current_layer}"
            self.drawing_state["last_result"] = "Success"
        else:
            self.drawing_state["last_result"] = "Failed"
        
        return result
    
    def draw_ellipse(self, center, major_axis, minor_axis, rotation=0, layer=None, color=None, lineweight=None):
        """Draw an ellipse"""
        if not self.controller.is_running():
            self.start_cad()
        
        # Use the current layer or the specified layer
        current_layer = layer or self.drawing_state["current_layer"]
        
        result = self.controller.draw_ellipse(center, major_axis, minor_axis, rotation, current_layer, color, lineweight)

        if result:
            self.drawing_state["entities"].append({
                "type": "ellipse",
                "center": center,
                "major_axis": major_axis,
                "minor_axis": minor_axis,
                "rotation": rotation,
                "layer": current_layer,
                "color": color,
                "lineweight": lineweight
            })
            self.drawing_state["last_command"] = f"Draw ellipse: center={center}; major axis={major_axis}; minor axis={minor_axis}; rotation={rotation}; layer={current_layer}"
            self.drawing_state["last_result"] = "Success"
        else:
            self.drawing_state["last_result"] = "Failed"
        
        return result
    
    def draw_polyline(self, points, closed=False, layer=None, color=None, lineweight=None):
        """Draw a polyline"""
        if not self.controller.is_running():
            self.start_cad()
        
        # Use the current layer or the specified layer
        current_layer = layer or self.drawing_state["current_layer"]
        
        result = self.controller.draw_polyline(points, closed, current_layer, color, lineweight)
        if result:
            self.drawing_state["entities"].append({
                "type": "polyline",
                "points": points,
                "closed": closed,
                "layer": current_layer,
                "color": color,
                "lineweight": lineweight
            })
            self.drawing_state["last_command"] = f"Draw polyline: points={points}, {'closed' if closed else 'open'}, layer={current_layer}"
            self.drawing_state["last_result"] = "Success"
        else:
            self.drawing_state["last_result"] = "Failed"
        
        return result
    
    def draw_rectangle(self, corner1, corner2, layer=None, color=None, lineweight=None):
        """Draw a rectangle"""
        if not self.controller.is_running():
            self.start_cad()
        
        # Use the current layer or the specified layer
        current_layer = layer or self.drawing_state["current_layer"]
        
        result = self.controller.draw_rectangle(corner1, corner2, current_layer, color, lineweight)
        if result:
            self.drawing_state["entities"].append({
                "type": "rectangle",
                "corner1": corner1,
                "corner2": corner2,
                "layer": current_layer,
                "color": color,
                "lineweight": lineweight
            })
            self.drawing_state["last_command"] = f"Draw rectangle: opposite corners={corner1} and {corner2}, layer={current_layer}"
            self.drawing_state["last_result"] = "Success"
        else:
            self.drawing_state["last_result"] = "Failed"
        
        return result
    
    def draw_text(self, position, text, height=2.5, rotation=0, layer=None, color=None):
        """Add text"""
        if not self.controller.is_running():
            self.start_cad()
        
        # Use the current layer or the specified layer
        current_layer = layer or self.drawing_state["current_layer"]
        
        result = self.controller.draw_text(position, text, height, rotation, current_layer, color)
        if result:
            self.drawing_state["entities"].append({
                "type": "text",
                "position": position,
                "text": text,
                "height": height,
                "rotation": rotation,
                "layer": current_layer,
                "color": color
            })
            self.drawing_state["last_command"] = f"Add text '{text}' at {position}; height={height}; rotation={rotation}"
            self.drawing_state["last_result"] = "Success"
        else:
            self.drawing_state["last_result"] = "Failed"
        
        return result
    
    def draw_hatch(self, points, pattern_name="SOLID", scale=1.0, layer=None, color=None):
        """Draw a hatch"""
        if not self.controller.is_running():
            self.start_cad()
        
        # Use the current layer or the specified layer
        current_layer = layer or self.drawing_state["current_layer"]
        
        result = self.controller.draw_hatch(points, pattern_name, scale, current_layer, color)
        if result:
            self.drawing_state["entities"].append({
                "type": "hatch",
                "points": points,
                "pattern_name": pattern_name,
                "scale": scale,
                "layer": current_layer,
                "color": color
            })
            self.drawing_state["last_command"] = f"Draw hatch: points={points}, pattern={pattern_name}, scale={scale}, layer={current_layer}"
            self.drawing_state["last_result"] = "Success"
        else:
            self.drawing_state["last_result"] = "Failed"
        
        return result
    
    def add_dimension(self, start_point, end_point, text_position=None,textheight=5, layer=None, color=None):
        """Add a linear dimension."""
        if not self.controller.is_running():
            self.start_cad()
        
        # Use the current layer or the specified layer
        current_layer = layer or self.drawing_state["current_layer"]
        
        result = self.controller.add_dimension(start_point, end_point, text_position, textheight,current_layer, color)
        if result:
            self.drawing_state["entities"].append({
                "type": "dimension",
                "start": start_point,
                "end": end_point,
                "text_position": text_position,
                "textheight": textheight,
                "layer": current_layer,
                "color": color
            })
            self.drawing_state["last_command"] = f"Add dimension from {start_point} to {end_point}"
            self.drawing_state["last_result"] = "Success"
        else:
            self.drawing_state["last_result"] = "Failed"
        
        return result
    

    def save_drawing(self, file_path):
        """Save the drawing"""
        if not self.controller.is_running():
            return False
        
        result = self.controller.save_drawing(file_path)
        if result:
            self.drawing_state["last_command"] = f"Save the drawing to {file_path}"
            self.drawing_state["last_result"] = "Success"
        else:
            self.drawing_state["last_result"] = "Failed"
        
        return result
    
    def process_command(self, command: str) -> Dict[str, Any]:
        """Process a natural language command"""
        if not self.controller.is_running():
            self.start_cad()
        # Parse the command with the NLP processor
        parsed_command = self.nlp_processor.process_command(command)
        command_type = parsed_command.get("type")
        try:
            # Handle basic drawing commands
            if command_type == "draw_line":
                start_point = parsed_command.get("start_point")
                end_point = parsed_command.get("end_point")
                # Get the color parameter
                color = parsed_command.get("color")
                # Try to extract a color name from the command and convert it to an RGB value
                color_rgb = self.nlp_processor.extract_color_from_command(command)
                if color_rgb is not None:
                    color = color_rgb  # Prefer the color extracted from the command
                # Get the lineweight parameter
                lineweight = parsed_command.get("lineweight")
                result = self.draw_line(start_point, end_point, None, color, lineweight)
                return {
                    "success": result is not None,
                    "message": "Line drawn" if result else "Failed to draw line",
                    "entity_id": result.Handle if result else None
                }

            ####################################################### addition
            elif command_type == "rename_blocks":
                prefix = parsed_command.get("prefix", "Block")
                filter_layer = parsed_command.get("filter", {}).get("layer")
                filter_block_name_prefix = parsed_command.get("filter", {}).get("block_name_prefix")

                success = self.controller.rename_blocks(
                    prefix=prefix,
                    filter_layer=filter_layer,
                    filter_block_name_prefix=filter_block_name_prefix
                )
                return {
                    "success": success,
                    "message": f"Blocks renamed with prefix '{prefix}'"
                }
            ########################################################

            elif command_type == "draw_circle":
                center = parsed_command.get("center")
                radius = parsed_command.get("radius")
                # Get the color parameter
                color = parsed_command.get("color")
                # Try to extract a color name from the command and convert it to an RGB value
                color_rgb = self.nlp_processor.extract_color_from_command(command)
                if color_rgb is not None:
                    color = color_rgb  # Prefer the color extracted from the command
                # Get the lineweight parameter
                lineweight = parsed_command.get("lineweight")
                result = self.draw_circle(center, radius, None, color, lineweight)
                return {
                    "success": result is not None,
                    "message": "Circle drawn" if result else "Failed to draw circle",
                    "entity_id": result.Handle if result else None
                }

            elif command_type == "draw_arc":
                center = parsed_command.get("center")
                radius = parsed_command.get("radius")
                start_angle = parsed_command.get("start_angle")
                end_angle = parsed_command.get("end_angle")
                # Ensure all required parameters are present and valid
                if center is None or radius is None or start_angle is None or end_angle is None:
                    return {
                        "success": False,
                        "message": "Failed to draw arc: required parameters are missing",
                        "error": "Missing required parameters: center, radius, start angle, or end angle"
                    }
                # Get the color parameter
                color = parsed_command.get("color")
                # Try to extract a color name from the command and convert it to an RGB value
                color_rgb = self.nlp_processor.extract_color_from_command(command)
                if color_rgb is not None:
                    color = color_rgb  # Prefer the color extracted from the command
                # Get the lineweight parameter
                lineweight = parsed_command.get("lineweight")
                result = self.draw_arc(center, radius, start_angle, end_angle, None, color, lineweight)

                return {
                    "success": result is not None,
                    "message": "Arc drawn" if result else "Failed to draw arc",
                    "entity_id": result.Handle if result else None
                }
                
            elif command_type == "draw_ellipse":
                center = parsed_command.get("center")
                major_axis = parsed_command.get("major_axis")
                minor_axis = parsed_command.get("minor_axis")
                rotation = parsed_command.get("rotation", 0)  # Default rotation angle is 0
                # Ensure all required parameters are present and valid
                if center is None or major_axis is None or minor_axis is None:
                    return {
                        "success": False,
                        "message": "Failed to draw ellipse: required parameters are missing",
                        "error": "Missing required parameters: center, major axis, or minor axis"
                    }
                # Get the color parameter
                color = parsed_command.get("color")
                # Try to extract a color name from the command and convert it to an RGB value
                color_rgb = self.nlp_processor.extract_color_from_command(command)
                if color_rgb is not None:
                    color = color_rgb  # Prefer the color extracted from the command
                # Get the lineweight parameter
                lineweight = parsed_command.get("lineweight")
                result = self.draw_ellipse(center, major_axis, minor_axis, rotation, None, color, lineweight)

                return {
                    "success": result is not None,
                    "message": "Ellipse drawn" if result else "Failed to draw ellipse",
                    "entity_id": result.Handle if result else None
                }

            elif command_type == "draw_rectangle":
                corner1 = parsed_command.get("corner1")
                corner2 = parsed_command.get("corner2")
                # Get the color parameter
                color = parsed_command.get("color")
                # Try to extract a color name from the command and convert it to an RGB value
                color_rgb = self.nlp_processor.extract_color_from_command(command)
                if color_rgb is not None:
                    color = color_rgb  # Prefer the color extracted from the command
                # Get the lineweight parameter
                lineweight = parsed_command.get("lineweight")
                result = self.draw_rectangle(corner1, corner2, None, color, lineweight)

                return {
                    "success": result is not None,
                    "message": "Rectangle drawn" if result else "Failed to draw rectangle",
                    "entity_id": result.Handle if result else None
                }

            elif command_type == "draw_text":
                position = parsed_command.get("position")
                text = parsed_command.get("text")
                height = parsed_command.get("height", 2.5)
                rotation = parsed_command.get("rotation", 0)
                # Get the color parameter
                color = parsed_command.get("color")
                # Try to extract a color name from the command and convert it to an RGB value
                color_rgb = self.nlp_processor.extract_color_from_command(command)
                if color_rgb is not None:
                    color = color_rgb  # Prefer the color extracted from the command
                result = self.draw_text(position, text, height, rotation, None, color)

                return {
                    "success": result is not None,
                    "message": "Text added" if result else "Failed to add text",
                    "entity_id": result.Handle if result else None
                }

            elif command_type == "draw_hatch":
                points = parsed_command.get("points")
                pattern_name = parsed_command.get("pattern_name", "SOLID")
                scale = parsed_command.get("scale", 1.0)
                # Ensure all required parameters are present and valid
                if points is None or len(points) < 3:
                    return {
                        "success": False,
                        "message": "Failed to draw hatch: required parameters are missing or there are too few points",
                        "error": "A hatch boundary requires at least 3 points"
                    }
                # Get the color parameter, which may be an index or an RGB value
                color = parsed_command.get("color")  # Get the color parameter
                # Try to extract a color name from the command and convert it to an RGB value
                color_rgb = self.nlp_processor.extract_color_from_command(command)
                if color_rgb is not None:
                    color = color_rgb  # Prefer the color extracted from the command
                result = self.draw_hatch(points, pattern_name, scale, None, color)

                return {
                    "success": result is not None,
                    "message": "Hatch drawn" if result else "Failed to draw hatch",
                    "entity_id": result.Handle if result else None
                }

            # Handle dimensions
            elif command_type == "add_dimension":
                start_point = parsed_command.get("start_point")
                end_point = parsed_command.get("end_point")
                text_position = parsed_command.get("text_position")
                result = self.controller.add_dimension(start_point, end_point, text_position)
                return {
                    "success": result is not None,
                    "message": "Dimension added" if result else "Failed to add dimension",
                    "entity_id": result.Handle if result else None
                }

            elif command_type == "save":
                file_path = parsed_command.get("file_path")
                result = self.save_drawing(file_path)

                return {
                    "success": result,
                    "message": f"Drawing saved to {file_path}" if result else f"Failed to save drawing to {file_path}"
                }


            # Handle layer operations
            elif command_type == "create_layer":
                layer_name = parsed_command.get("layer_name")
                color = parsed_command.get("color", 7)  # White by default.
                result = self.controller.create_layer(layer_name)  # , color
                return {
                    "success": result,
                    "message": f"Layer {layer_name} created" if result else f"Failed to create layer {layer_name}"
                }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Error processing command: {str(e)}"
            }

async def main():
    """Main entry point"""
    logger.info("Starting the CAD MCP server")

    # Load configuration
    config = Config()
    cad_service = CADService()
    server = Server(config.server_name)

    # Register handlers
    logger.debug("Register handlers")

    @server.list_resources()
    async def handle_list_resources() -> list[types.Resource]:
        logger.debug("Handling list_resources request")
        return [
            types.Resource(
                uri=AnyUrl("drawing://current"),
                name="Current CAD drawing",
                description="Current CAD drawing state",
                mimeType="application/json",
            )
        ]

    @server.read_resource()
    async def handle_read_resource(uri: AnyUrl) -> str:
        logger.debug(f"Handling read_resource request, URI: {uri}")
        if uri.scheme != "drawing":
            logger.error(f"Unsupported URI scheme: {uri.scheme}")
            raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

        path = str(uri).replace("drawing://", "")
        if not path or path != "current":
            logger.error(f"Unknown resource path: {path}")
            raise ValueError(f"Unknown resource path: {path}")

        return json.dumps(cad_service.drawing_state)


    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        """List available tools"""
        return [
            types.Tool(
                name="draw_line",
                description="Draw a line in CAD",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "start_point": {
                            "type": "array",
                            "description": "Start point coordinates [x, y, z]",
                            "items": {"type": "number"},
                            "minItems": 2,
                            "maxItems": 3
                        },
                        "end_point": {
                            "type": "array",
                            "description": "End point coordinates [x, y, z]",
                            "items": {"type": "number"},
                            "minItems": 2,
                            "maxItems": 3
                        },
                        "layer": {"type": "string", "description": "Layer name (optional)"},
                        "color": {"type": "string", "description": "Color name (optional)"},
                        "lineweight": {"type": "number", "description": "Lineweight (optional)"}
                    },
                    "required": ["start_point", "end_point"],
                },
            ),

            ###################################### addition
            types.Tool(
                name="rename_blocks",
                description="Rename blocks with a prefix, optionally filtered by layer or block name prefix",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prefix": {"type": "string", "description": "Prefix for new block names"},
                        "filter": {
                            "type": "object",
                            "properties": {
                                "layer": {"type": "string",
                                          "description": "Only rename blocks containing entities on this layer"},
                                "block_name_prefix": {"type": "string",
                                                      "description": "Only rename blocks starting with this name prefix"}
                            }
                        }
                    },
                    "required": ["prefix"]
                }
            ),
            ######################################

            types.Tool(
                name="draw_circle",
                description="Draw a circle in CAD",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "center": {
                            "type": "array",
                            "description": "Center coordinates [x, y, z]",
                            "items": {"type": "number"},
                            "minItems": 2,
                            "maxItems": 3
                        },
                        "radius": {"type": "number", "description": "Circle radius"},
                        "layer": {"type": "string", "description": "Layer name (optional)"},
                        "color": {"type": "string", "description": "Color name (optional)"},
                        "lineweight": {"type": "number", "description": "Lineweight (optional)"}
                    },
                    "required": ["center", "radius"],
                },
            ),

            types.Tool(
                name="draw_arc",
                description="Draw an arc in CAD",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "center": {
                            "type": "array",
                            "description": "Center coordinates [x, y, z]",
                            "items": {"type": "number"},
                            "minItems": 2,
                            "maxItems": 3
                        },
                        "radius": {"type": "number", "description": "Arc radius"},
                        "start_angle": {"type": "number", "description": "Start angle (degrees)"},
                        "end_angle": {"type": "number", "description": "End angle (degrees)"},
                        "layer": {"type": "string", "description": "Layer name (optional)"},
                        "color": {"type": "string", "description": "Color name (optional)"},
                        "lineweight": {"type": "number", "description": "Lineweight (optional)"}
                    },
                    "required": ["center", "radius", "start_angle", "end_angle"],
                },
            ),

            types.Tool(
                name="draw_ellipse",
                description="Draw an ellipse in CAD",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "center": {
                            "type": "array",
                            "description": "Ellipse center coordinates [x, y, z]",
                            "items": {"type": "number"},
                            "minItems": 2,
                            "maxItems": 3
                        },
                        "major_axis": {"type": "number", "description": "Major axis length"},
                        "minor_axis": {"type": "number", "description": "Minor axis length"},
                        "rotation": {"type": "number", "description": "Rotation angle (degrees, optional)"},
                        "layer": {"type": "string", "description": "Layer name (optional)"},
                        "color": {"type": "string", "description": "Color name (optional)"},
                        "lineweight": {"type": "number", "description": "Lineweight (optional)"}
                    },
                    "required": ["center", "major_axis", "minor_axis"],
                },
            ),

            types.Tool(
                name="draw_polyline",
                description="Draw a polyline in CAD",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "points": {
                            "type": "array",
                            "description": "Point list [[x1, y1, z1], [x2, y2, z2], ...]",
                            "items": {
                                "type": "array",
                                "items": {"type": "number"},
                                "minItems": 2,
                                "maxItems": 3
                            },
                            "minItems": 2
                        },
                        "closed": {"type": "boolean", "description": "Whether to close the polyline"},
                        "layer": {"type": "string", "description": "Layer name (optional)"},
                        "color": {"type": "string", "description": "Color name (optional)"},
                        "lineweight": {"type": "number", "description": "Lineweight (optional)"}
                    },
                    "required": ["points"],
                },
            ),

            types.Tool(
                name="draw_rectangle",
                description="Draw a rectangle in CAD",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "corner1": {
                            "type": "array",
                            "description": "First corner coordinates [x, y, z]",
                            "items": {"type": "number"},
                            "minItems": 2,
                            "maxItems": 3
                        },
                        "corner2": {
                            "type": "array",
                            "description": "Second corner coordinates [x, y, z]",
                            "items": {"type": "number"},
                            "minItems": 2,
                            "maxItems": 3
                        },
                        "layer": {"type": "string", "description": "Layer name (optional)"},
                        "color": {"type": "string", "description": "Color name (optional)"},
                        "lineweight": {"type": "number", "description": "Lineweight (optional)"}
                    },
                    "required": ["corner1", "corner2"],
                },
            ),

            types.Tool(
                name="draw_text",
                description="Add text in CAD",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "position": {
                            "type": "array",
                            "description": "Insertion point coordinates [x, y, z]",
                            "items": {"type": "number"},
                            "minItems": 2,
                            "maxItems": 3
                        },
                        "text": {"type": "string", "description": "Text content"},
                        "height": {"type": "number", "description": "Text height"},
                        "rotation": {"type": "number", "description": "Rotation angle (degrees)"},
                        "layer": {"type": "string", "description": "Layer name (optional)"},
                        "color": {"type": "string", "description": "Color name (optional)"}
                    },
                    "required": ["position", "text"],
                },
            ),
           
            types.Tool(
                name="draw_hatch",
                description="Draw a hatch in CAD",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "points": {
                            "type": "array",
                            "description": "Hatch boundary point list [[x1, y1, z1], [x2, y2, z2], ...]",
                            "items": {
                                "type": "array",
                                "items": {"type": "number"},
                                "minItems": 2,
                                "maxItems": 3
                            },
                            "minItems": 3
                        },
                        "pattern_name": {"type": "string", "description": "Hatch pattern name (optional, defaults to SOLID)"},
                        "scale": {"type": "number", "description": "Hatch pattern scale (optional, defaults to 1.0)"},
                        "layer": {"type": "string", "description": "Layer name (optional)"},
                        "color": {"type": "string", "description": "Color name (optional)"}
                    },
                    "required": ["points"],
                },
            ),

            types.Tool(
                name="add_dimension",
                description="Add a linear dimension in CAD",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "start_point": {"type": "array", "description": "Start point coordinates [x, y, z]", "items": {"type": "number"}, "minItems": 2, "maxItems": 3},
                        "end_point": {"type": "array", "description": "End point coordinates [x, y, z]", "items": {"type": "number"}, "minItems": 2, "maxItems": 3},
                        "text_position": {"type": "array", "description": "Text position coordinates [x, y, z] (optional)", "items": {"type": "number"}, "minItems": 2, "maxItems": 3},
                        "textheight": {"type": "number", "description": "Dimension text height (optional)"},
                        "layer": {"type": "string", "description": "Layer name (optional)"},
                        "color": {"type": "string", "description": "Color name (optional)"}
                    },
                    "required": ["start_point", "end_point"],
                },
            ),

            types.Tool(
                name="save_drawing",
                description="Save the current drawing",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Save path"}
                    },
                    "required": ["file_path"],
                },
            ),

            types.Tool(
                name="process_command",
                description="Process a natural language command and convert it to a CAD operation",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Natural language command"}
                    },
                    "required": ["command"],
                },
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """Handle a tool execution request"""
        try:
            if not arguments:
                raise ValueError("Missing parameters")

            if name == "draw_line":
                start_point = arguments.get("start_point")
                end_point = arguments.get("end_point")
                layer = arguments.get("layer")
                color = arguments.get("color") 
                lineweight = arguments.get("lineweight")
                
                # Try to extract a color name from the command and convert it to an RGB value
                color_rgb = cad_service.nlp_processor.extract_color_from_command(color)
                if color_rgb is not None:
                    color = color_rgb  # Prefer the color extracted from the command
                
                if not start_point or not end_point:
                    raise ValueError("Missing start or end point coordinates")
                
                
                result = cad_service.draw_line(start_point, end_point, layer, color, lineweight)
                return [types.TextContent(type="text", text=str(result))]

            elif name == "draw_circle":
                center = arguments.get("center")
                radius = arguments.get("radius")
                layer = arguments.get("layer")
                color = arguments.get("color")
                lineweight = arguments.get("lineweight")
                
                # Try to extract a color name from the command and convert it to an RGB value
                color_rgb = cad_service.nlp_processor.extract_color_from_command(color)
                if color_rgb is not None:
                    color = color_rgb  # Prefer the color extracted from the command
                
                if not center or radius is None:
                    raise ValueError("Missing center coordinates or radius")
                
                
                result = cad_service.draw_circle(center, radius, layer, color, lineweight)
                return [types.TextContent(type="text", text=str(result))]

            elif name == "draw_arc":
                center = arguments.get("center")
                radius = arguments.get("radius")
                start_angle = arguments.get("start_angle")
                end_angle = arguments.get("end_angle")
                layer = arguments.get("layer")
                color = arguments.get("color")
                lineweight = arguments.get("lineweight")
                
                # Try to extract a color name from the command and convert it to an RGB value
                color_rgb = cad_service.nlp_processor.extract_color_from_command(color)
                if color_rgb is not None:
                    color = color_rgb  # Prefer the color extracted from the command
                
                # Check each parameter and provide a specific error message
                error_msgs = []
                if not center:
                    error_msgs.append("Center coordinates")
                if radius is None:
                    error_msgs.append("Radius")
                if start_angle is None:
                    error_msgs.append("Start angle")
                if end_angle is None:
                    error_msgs.append("End angle")
                
                if error_msgs:
                    raise ValueError(f"Missing required parameters: {', '.join(error_msgs)}")
                
                result = cad_service.draw_arc(center, radius, start_angle, end_angle, layer, color, lineweight)
                return [types.TextContent(type="text", text=str(result))]

            elif name == "draw_ellipse":
                center = arguments.get("center")
                major_axis = arguments.get("major_axis")
                minor_axis = arguments.get("minor_axis")
                rotation = arguments.get("rotation")
                layer = arguments.get("layer")
                color = arguments.get("color")
                lineweight = arguments.get("lineweight")
                
                # Try to extract a color name from the command and convert it to an RGB value
                color_rgb = cad_service.nlp_processor.extract_color_from_command(color)
                if color_rgb is not None:
                    color = color_rgb  # Prefer the color extracted from the command
                
                # Check each parameter and provide a specific error message
                error_msgs = []
                if not center:
                    error_msgs.append("Center coordinates")
                if major_axis is None:
                    error_msgs.append("Major axis")
                if minor_axis is None:
                    error_msgs.append("Minor axis")
                
                if error_msgs:
                    raise ValueError(f"Missing required parameters: {', '.join(error_msgs)}")
                
                result = cad_service.draw_ellipse(center, major_axis, minor_axis, rotation, layer, color, lineweight)
                return [types.TextContent(type="text", text=str(result))]

            elif name == "draw_polyline":
                points = arguments.get("points")
                closed = arguments.get("closed", False)
                layer = arguments.get("layer")
                color = arguments.get("color")
                lineweight = arguments.get("lineweight")
                
                # Try to extract a color name from the command and convert it to an RGB value
                color_rgb = cad_service.nlp_processor.extract_color_from_command(color)
                if color_rgb is not None:
                    color = color_rgb  # Prefer the color extracted from the command
                
                if not points or len(points) < 2:
                    raise ValueError("Missing point list or too few points")
                
                result = cad_service.draw_polyline(points, closed, layer, color, lineweight)
                return [types.TextContent(type="text", text=str(result))]

            elif name == "draw_rectangle":
                corner1 = arguments.get("corner1")
                corner2 = arguments.get("corner2")
                layer = arguments.get("layer")
                color = arguments.get("color")
                lineweight = arguments.get("lineweight")
                
                # Try to extract a color name from the command and convert it to an RGB value
                color_rgb = cad_service.nlp_processor.extract_color_from_command(color)
                if color_rgb is not None:
                    color = color_rgb  # Prefer the color extracted from the command
                
                if not corner1 or not corner2:
                    raise ValueError("Missing corner coordinates")
                
                result = cad_service.draw_rectangle(corner1, corner2, layer, color, lineweight)
                return [types.TextContent(type="text", text=str(result))]


            elif name == "draw_text":
                position = arguments.get("position")
                text = arguments.get("text")
                height = arguments.get("height", 2.5)
                rotation = arguments.get("rotation", 0)
                layer = arguments.get("layer")
                color = arguments.get("color")
                
                # Try to extract a color name from the command and convert it to an RGB value
                color_rgb = cad_service.nlp_processor.extract_color_from_command(color)
                if color_rgb is not None:
                    color = color_rgb  # Prefer the color extracted from the command
                
                if not position or not text:
                    raise ValueError("Missing insertion point coordinates or text content")
                
                result = cad_service.draw_text(position, text, height, rotation, layer, color)
                return [types.TextContent(type="text", text=str(result))]


            elif name == "draw_hatch":
                points = arguments.get("points")
                pattern_name = arguments.get("pattern_name", "SOLID")
                scale = arguments.get("scale", 1.0)
                layer = arguments.get("layer")
                color = arguments.get("color")
                
                # Try to extract a color name from the command and convert it to an RGB value
                color_rgb = cad_service.nlp_processor.extract_color_from_command(color)
                if color_rgb is not None:
                    color = color_rgb  # Prefer the color extracted from the command
                
                if not points or len(points) < 3:
                    raise ValueError("Missing point list or too few points; a hatch boundary requires at least 3 points")
                
                result = cad_service.draw_hatch(points, pattern_name, scale, layer, color)
                return [types.TextContent(type="text", text=str(result))]

            elif name == "save_drawing":
                file_path = arguments.get("file_path")
                
                if not file_path:
                    raise ValueError("Missing save path")
                
                result = cad_service.save_drawing(file_path)
                return [types.TextContent(type="text", text=str(result))]

            elif name == "add_dimension":
                start_point = arguments.get("start_point")
                end_point = arguments.get("end_point")
                text_position = arguments.get("text_position")
                layer = arguments.get("layer")
                color = arguments.get("color")
                textheight = arguments.get("textheight")                

                # Try to extract a color name from the command and convert it to an RGB value
                color_rgb = cad_service.nlp_processor.extract_color_from_command(color)
                if color_rgb is not None:
                    color = color_rgb  # Prefer the color extracted from the command

                # Check each parameter and provide a specific error message
                error_msgs = []
                if not start_point:
                    error_msgs.append("Start point coordinates")
                if not end_point:
                    error_msgs.append("End point coordinates")

                if error_msgs:
                    raise ValueError(f"Missing required parameters: {', '.join(error_msgs)}")

                result = cad_service.add_dimension(start_point, end_point, text_position, textheight, layer, color)
                return [types.TextContent(type="text", text=str(result))]

            elif name == "process_command":
                command = arguments.get("command")                

                if not command:
                    raise ValueError("Missing command")

                result = cad_service.process_command(command)
                return [types.TextContent(type="text", text=str(result))]
            else:
                raise ValueError(f"Unknown tool: {name}")

        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    @server.list_prompts()
    async def handle_list_prompts() -> list[types.Prompt]:
        logger.debug("Handling list_prompts request")
        return [
            types.Prompt(
                name="cad-assistant",
                description="An assistant for controlling CAD through natural language",
                arguments=[],
            )
        ]

    @server.get_prompt()
    async def handle_get_prompt(name: str, arguments: dict[str, str] | None) -> types.GetPromptResult:
        logger.debug(f"Handling get_prompt request, name: {name}; arguments: {arguments}")
        if name != "cad-assistant":
            logger.error(f"Unknown prompt: {name}")
            raise ValueError(f"Unknown prompt: {name}")

        prompt = PROMPT_TEMPLATE
        logger.debug("Generating the prompt template")

        return types.GetPromptResult(
            description="CAD assistant prompt template",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(type="text", text=prompt.strip()),
                )
            ],
        )

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        logger.info("Server is running with stdio transport")
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=config.server_name,
                server_version=config.server_version,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
