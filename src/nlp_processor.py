import logging
import re
import math
from typing import Any, Dict, List, Optional, Tuple
import json
import os
import os.path

# Read config.json directly
config_path = os.path.join(os.path.dirname(__file__), 'config.json')
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

logger = logging.getLogger('nlp_processor')

class NLPProcessor:
    """Parse user instructions and convert them into CAD operations."""
    
    def __init__(self):
        """
        Initialize the NLP processor.
        """
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("NLP processor initialized")

        # Older CAD versions do not support RGB colors, so use indexed colors for compatibility.
        
        # Map color names to CAD color indices.
        self.color_rgb_map = {
            "red": 1,
            "yellow": 2,
            "green": 3,
            "cyan": 4,
            "blue": 5,
            "magenta": 6,
            "white": 7,
            "gray": 8,
            "light gray": 9,
            "black": 250,
            "brown": 251,
            "orange": 30,
            "purple": 200,
            "pink": 221,
                       
        }
        
        # Map common shape terms to CAD entities.
        self.shape_keywords = {
            "line": "line", "lines": "line",
            "circle": "circle", "circles": "circle",
            "arc": "arc", "arcs": "arc",
            "rectangle": "rectangle", "square": "square",
            "polyline": "polyline", "polygon": "polyline",
            "text": "text", "label": "text",
            "dimension": "dimension", "dimensions": "dimension",
            
        }
        
        # Map common action terms to operations.
        self.action_keywords = {
            "draw": "draw", "create": "draw", "add": "draw", "make": "draw",
            "modify": "modify", "adjust": "modify", "change": "modify",
            "move": "move", "rotate": "rotate", "scale": "scale",
            "enlarge": "scale_up", "shrink": "scale_down",
            "delete": "erase", "erase": "erase", "remove": "erase",
            "save": "save",
            
            # Specialized operations.
            "dimension": "dimension",
            "hatch": "hatch",
            "create layer": "create_layer",
            "change layer": "change_layer"
        }
    
      
    def extract_color_from_command(self, command: str) -> Optional[int]:
       
        if command is None:
            return 7

        try:
            num = int(command)
            if num >= 1 and num <= 255:
                return num
        except:
            pass

        # Normalize the command to lowercase.
        command = command.lower()
        
        # Try to match a color name.
        for color_name in self.color_rgb_map.keys():
            if color_name.lower() in command:
                return self.color_rgb_map[color_name]
        
        # Try to match a color description such as "light blue".
        color_pattern = r'([a-zA-Z ]+)'
        color_matches = re.findall(color_pattern, command)
        
        for color_match in color_matches:
            # Check whether this is a known color name.
            if color_match in self.color_rgb_map:
                return self.color_rgb_map[color_match]
                    
        # Return 7 (white) when no color is found.
        return 7
    
    def process_command(self, command: str) -> Dict[str, Any]:
        """Process a natural language command and return the result."""
        self.logger.info(f"Processing command: {command}")
        if "block" in command and any(k in command for k in ["rename", "change name"]):
            return self._parse_rename_blocks(command)
        # Parse the command.
        parsed_command = self.parse_command(command)
      
        # Return the parsed command.
        return parsed_command
    
    def parse_command(self, command: str) -> Dict[str, Any]:
        """Parse a natural language command into CAD operation parameters."""
        self.logger.info(f"Parsing command: {command}")
        
        # Convert the command to lowercase and remove extra whitespace.
        command = command.lower().strip()
        
        # Try to identify the command type.
        command_type = self._identify_command_type(command)
        self.logger.debug(f"Identified command type: {command_type}")
        
        # Dispatch to the handler for this command type.
        if command_type == "draw_line":
            return self._parse_draw_line(command)
        elif command_type == "draw_circle":
            return self._parse_draw_circle(command)
        elif command_type == "draw_arc":
            return self._parse_draw_arc(command)
        elif command_type == "draw_rectangle":
            return self._parse_draw_rectangle(command)
        elif command_type == "draw_polyline":
            return self._parse_draw_polyline(command)
        elif command_type == "draw_text":
            return self._parse_draw_text(command)
        elif command_type == "draw_hatch":
            return self._parse_draw_hatch(command)
        elif command_type == "save":
            return self._parse_save(command)

        #################################### addition
        elif command_type == "rename_blocks":
            return self._parse_rename_blocks(command)
        ####################################


        else:
            # Return an error when the command type is unknown.
            return {
                "type": "unknown",
                "error": "Unrecognized command type",
                "original_command": command
            }
    
    def _identify_command_type(self, command: str) -> str:
        """Identify the command type."""
        # Check for an action and shape combination.
        for action, action_type in self.action_keywords.items():
            if action in command:
                # Handle basic shapes.
                for shape, shape_type in self.shape_keywords.items():
                    if shape in command:
                        if action_type == "draw":
                            if shape_type == "line":
                                return "draw_line"
                            elif shape_type == "circle":
                                return "draw_circle"
                            elif shape_type == "arc":
                                return "draw_arc"
                            elif shape_type in ["rectangle", "square"]:
                                return "draw_rectangle"
                            elif shape_type == "polyline":
                                return "draw_polyline"
                            elif shape_type == "text":
                                return "draw_text"
                            elif shape_type == "dimension":
                                return "add_dimension"
        
        # Check for layer creation commands.
        if "layer" in command and any(action in command for action in ["create", "add", "make"]):
            return "create_layer"

        ########################################## addition
        if "block" in command and any(
                keyword in command for keyword in ["rename", "change name"]):
            return "rename_blocks"
        ##########################################

        # Check for dimension commands.
        if "dimension" in command:
            return "add_dimension"
        ########################################## addition
        if "save" in command:
            return "save"
        ##########################################

        if "save" in command:
            return "save"
        
        # Return unknown if no command type matches.
        return "unknown"
    
    def _extract_coordinates(self, text: str) -> List[Tuple[float, float, float]]:
        """Extract coordinate points from text."""
        # Match coordinates in (x,y,z), (x,y), x,y,z, or x,y format.
        pattern = r'\(?\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)(?:\s*,\s*(-?\d+\.?\d*))?\s*\)?'
        matches = re.finditer(pattern, text)
        
        coordinates = []
        for match in matches:
            x = float(match.group(1))
            y = float(match.group(2))
            z = float(match.group(3)) if match.group(3) else 0.0
            coordinates.append((x, y, z))
        
        return coordinates
    
    def _extract_numbers(self, text: str) -> List[float]:
        """Extract numbers from text."""
        pattern = r'(-?\d+\.?\d*)'
        matches = re.findall(pattern, text)
        return [float(match) for match in matches]
    
    def _parse_draw_line(self, command: str) -> Dict[str, Any]:
        """Parse a line drawing command."""
        # Try to extract coordinates.
        coordinates = self._extract_coordinates(command)
        
        if len(coordinates) >= 2:
            # Use the first two points as the start and end when available.
            return {
                "type": "draw_line",
                "start_point": coordinates[0],
                "end_point": coordinates[1]
            }
        else:
            # Use default coordinates if the command does not contain enough points.
            return {
                "type": "draw_line",
                "start_point": (0, 0, 0),
                "end_point": (100, 100, 0),
                "note": "Using default coordinates because the command did not provide enough points"
            }
    
    def _parse_draw_circle(self, command: str) -> Dict[str, Any]:
        """Parse a circle drawing command."""
        # Try to extract coordinates and the radius.
        coordinates = self._extract_coordinates(command)
        numbers = self._extract_numbers(command)
        
        # Extract the radius.
        radius = None
        radius_pattern = r'(?:radius|r)[^\d]*?(-?\d+\.?\d*)'
        radius_match = re.search(radius_pattern, command, re.IGNORECASE)
        if radius_match:
            radius = float(radius_match.group(1))
        elif len(numbers) > 0:
            # Use the first number as the radius if none is specified explicitly.
            radius = numbers[0]
        else:
            # Default radius.
            radius = 50.0
        
        # Extract the center point.
        center = None
        if len(coordinates) > 0:
            center = coordinates[0]
        else:
            # Default center point.
            center = (0, 0, 0)
        
        return {
            "type": "draw_circle",
            "center": center,
            "radius": radius
        }
    
    def _parse_draw_arc(self, command: str) -> Dict[str, Any]:
        """Parse an arc drawing command."""
        # Try to extract coordinates, the radius, and the angles.
        coordinates = self._extract_coordinates(command)
        numbers = self._extract_numbers(command)
        
        # Extract the center point.
        center = None
        if len(coordinates) > 0:
            center = coordinates[0]
        else:
            # Default center point.
            center = (0, 0, 0)
        
        # Extract the radius.
        radius = None
        radius_pattern = r'(?:radius|r)[^\d]*?(-?\d+\.?\d*)'
        radius_match = re.search(radius_pattern, command, re.IGNORECASE)
        if radius_match:
            radius = float(radius_match.group(1))
        elif len(numbers) > 0:
            # Use the first number as the radius if none is specified explicitly.
            radius = numbers[0]
        else:
            # Default radius.
            radius = 50.0
        
        # Extract the start and end angles.
        start_angle = 0.0
        end_angle = 90.0
        
        start_angle_pattern = r'(?:start angle|start)[^\d]*?(-?\d+\.?\d*)'
        start_angle_match = re.search(start_angle_pattern, command, re.IGNORECASE)
        if start_angle_match:
            start_angle = float(start_angle_match.group(1))
        
        end_angle_pattern = r'(?:end angle|end)[^\d]*?(-?\d+\.?\d*)'
        end_angle_match = re.search(end_angle_pattern, command, re.IGNORECASE)
        if end_angle_match:
            end_angle = float(end_angle_match.group(1))
        
        # Ensure all required parameters have values.
        if center is None:
            center = (0, 0, 0)
        if radius is None:
            radius = 50.0
        if start_angle is None:
            start_angle = 0.0
        if end_angle is None:
            end_angle = 90.0
            
        self.logger.debug(f"Parsed arc command: center={center}, radius={radius}, start angle={start_angle}, end angle={end_angle}")
        
        return {
            "type": "draw_arc",
            "center": center,
            "radius": radius,
            "start_angle": start_angle,
            "end_angle": end_angle
        }
    
    def _parse_draw_rectangle(self, command: str) -> Dict[str, Any]:
        """Parse a rectangle drawing command."""
        # Try to extract coordinates.
        coordinates = self._extract_coordinates(command)
        
        if len(coordinates) >= 2:
            # Use the first two points as opposite corners when available.
            return {
                "type": "draw_rectangle",
                "corner1": coordinates[0],
                "corner2": coordinates[1]
            }
        else:
            # Try to extract the width and height if there are not enough points.
            width = 100.0
            height = 100.0
            
            width_pattern = r'(?:width|w)[^\d]*?(-?\d+\.?\d*)'
            width_match = re.search(width_pattern, command, re.IGNORECASE)
            if width_match:
                width = float(width_match.group(1))
            
            height_pattern = r'(?:height|h)[^\d]*?(-?\d+\.?\d*)'
            height_match = re.search(height_pattern, command, re.IGNORECASE)
            if height_match:
                height = float(height_match.group(1))
            
            # Use the one available point as the first corner.
            if len(coordinates) == 1:
                corner1 = coordinates[0]
                corner2 = (corner1[0] + width, corner1[1] + height, corner1[2])
            else:
                # Default start and end points.
                corner1 = (0, 0, 0)
                corner2 = (width, height, 0)
            
            return {
                "type": "draw_rectangle",
                "corner1": corner1,
                "corner2": corner2
            }
    
    def _parse_draw_polyline(self, command: str) -> Dict[str, Any]:
        """Parse a polyline drawing command."""
        # Try to extract coordinates.
        coordinates = self._extract_coordinates(command)
        
        # Check whether the polyline should be closed.
        closed = "closed" in command or "close" in command
        
        if len(coordinates) >= 2:
            # Use the available points when at least two are present.
            return {
                "type": "draw_polyline",
                "points": coordinates,
                "closed": closed
            }
        else:
            # Return an error if there are not enough points.
            return {
                "type": "error",
                "message": "A polyline requires at least two coordinate points"
            }
    
    def _parse_draw_text(self, command: str) -> Dict[str, Any]:
        """Parse a text drawing command."""
        # Try to extract coordinates.
        coordinates = self._extract_coordinates(command)
        
        # Extract the text content.
        text_pattern = r'(?:text|content)\s*[:=]\s*[\"\'](.*?)[\"\']'
        text_match = re.search(text_pattern, command)
        
        text = ""
        if text_match:
            text = text_match.group(1)
        else:
            # Use quoted content as the text if available.
            quote_pattern = r'[\"\'](.*?)[\"\']'
            quote_match = re.search(quote_pattern, command)
            if quote_match:
                text = quote_match.group(1)
            else:
                # Use default text if no quoted content was found.
                text = "Example text"
        
        # Extract the text height.
        height = 2.5  # Default height.
        height_pattern = r'(?:height|h)[^\d]*?(-?\d+\.?\d*)'
        height_match = re.search(height_pattern, command, re.IGNORECASE)
        if height_match:
            height = float(height_match.group(1))
        
        # Extract the rotation angle.
        rotation = 0.0  # Default angle.
        rotation_pattern = r'(?:rotation|angle)[^\d]*?(-?\d+\.?\d*)'
        rotation_match = re.search(rotation_pattern, command, re.IGNORECASE)
        if rotation_match:
            rotation = float(rotation_match.group(1))
        
        # Extract the insertion point.
        position = None
        if len(coordinates) > 0:
            position = coordinates[0]
        else:
            # Default insertion point.
            position = (0, 0, 0)
        
        return {
            "type": "draw_text",
            "position": position,
            "text": text,
            "height": height,
            "rotation": rotation
        }
    
    def _parse_draw_hatch(self, command: str) -> Dict[str, Any]:
        """Parse a hatch drawing command."""
        # Try to extract the boundary points.
        coordinates = self._extract_coordinates(command)
        
        # Extract the hatch pattern name.
        pattern_name = "SOLID"  # Default to a solid fill.
        pattern_patterns = [
            r"""pattern[^\w]*?["'](.*?)["']""",
            r'pattern[^\w]*?(\w+)'
        ]
        
        for pattern in pattern_patterns:
            pattern_match = re.search(pattern, command, re.IGNORECASE)
            if pattern_match:
                pattern_name = pattern_match.group(1).upper()
                break
        
        # Extract the hatch scale.
        scale = 1.0  # Default scale.
        scale_pattern = r'(?:scale)[^\d]*?(\d+\.?\d*)'
        scale_match = re.search(scale_pattern, command, re.IGNORECASE)
        if scale_match:
            scale = float(scale_match.group(1))
        
        # Check that there are enough points to define the hatch boundary.
        if len(coordinates) >= 3:
            self.logger.debug(f"Parsed hatch command: points={coordinates}, pattern={pattern_name}, scale={scale}")
            return {
                "type": "draw_hatch",
                "points": coordinates,
                "pattern_name": pattern_name,
                "scale": scale
            }
        else:
            # Return an error if there are not enough points.
            self.logger.warning("Could not parse hatch command: at least 3 points are required to define the boundary")
            return {
                "type": "error",
                "message": "A hatch requires at least 3 points to define its boundary"
            }


    def _parse_save(self, command: str) -> Dict[str, Any]:
        """Parse a save command."""
        # Try to extract the file path.
        path_pattern = r'(?:path|save to)[^\w]*?[\"\'](.*?)[\"\']'
        path_match = re.search(path_pattern, command, re.IGNORECASE)
        
        if path_match:
            file_path = path_match.group(1)
        else:
            # Use the configured default file path.
            file_path = os.path.join(config["output"]["directory"], config["output"]["default_filename"])
        
        return {
            "type": "save",
            "file_path": file_path
        }
#################################################### addition

    def _parse_rename_blocks(self, command: str) -> dict:
        """Extract parameters for renaming blocks"""
        import re

        prefix_match = re.search(r"prefix\s+(\w+)", command)
        prefix = prefix_match.group(1) if prefix_match else "Block"

        layer_match = re.search(r"layer\s+(\w+)", command)
        block_layer = layer_match.group(1) if layer_match else None

        name_prefix_match = re.search(r"block name prefix\s+(\w+)", command)
        name_prefix = name_prefix_match.group(1) if name_prefix_match else None

        return {
            "type": "rename_blocks",
            "prefix": prefix,
            "filter": {
                "layer": block_layer,
                "block_name_prefix": name_prefix
            }
        }
#################################################
