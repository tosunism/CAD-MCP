import logging
import math
import time
import os
import json
from typing import Any, Dict, List, Optional, Tuple, Union

# Read config.json directly
config_path = os.path.join(os.path.dirname(__file__), 'config.json')
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

try:
    import win32com.client
    # pythoncom is included with pywin32 and does not need to be installed separately
    import pythoncom
except ImportError:
    logging.error("Could not import win32com.client or pythoncom. Make sure pywin32 is installed.")
    raise

logger = logging.getLogger('cad_controller')

class CADController:
    """CAD controller for interacting with the CAD application"""
    
    def __init__(self):
        """Initialize the CAD controller"""
        self.app = None
        self.doc = None
        self.entities = {}  # Store references to created drawing entities for later modification
        # Load settings from the configuration file
        self.startup_wait_time = config["cad"]["startup_wait_time"]
        self.command_delay = config["cad"]["command_delay"]
        # Get the CAD application type
        self.cad_type = config["cad"]["type"]
        # List of valid lineweight values
        self.valid_lineweights = [0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200, 211]
        logger.info("CAD controller initialized")

    def start_cad(self) -> bool:
        """Start CAD and create or open a document"""
        try:
            # Initialize COM
            pythoncom.CoInitialize()
            
            # Keep a reference to the previous instance, if any, for cleanup
            old_app = None
            if self.app is not None:
                old_app = self.app
                self.app = None
                self.doc = None
            
            try:
                # Select the application identifier based on the configured CAD type
                app_id = "AutoCAD.Application"
                app_name = "AutoCAD"
                
                if self.cad_type.lower() == "autocad":
                    app_id = "AutoCAD.Application"
                    app_name = "AutoCAD"
                elif self.cad_type.lower() == "gcad":
                    app_id = "GCAD.Application"
                    app_name = "GstarCAD"
                elif self.cad_type.lower() == "gstarcad":
                    app_id = "GCAD.Application"
                    app_name = "GstarCAD"
                elif self.cad_type.lower() == "zwcad":
                    app_id = "ZWCAD.Application"
                    app_name = "ZWCAD"
                
                # Try to connect to a running CAD instance
                logger.info(f"Trying to connect to the existing {app_name} instance...")
                try:
                    self.app = win32com.client.GetActiveObject(app_id)
                    logger.info(f"Connected to the running {app_name} instance")
                except Exception as e:
                    logger.info(f"No running {app_name} instance found; trying to start a new instance: {str(e)}")
                    raise

                # Already handled above
                
                # Create a new document if there is no current document
                try:
                    if self.app.Documents.Count == 0:
                        logger.info("Creating a new document...")
                        self.doc = self.app.Documents.Add()
                    else:
                        logger.info("Getting the active document...")
                        self.doc = self.app.ActiveDocument
                except Exception as doc_ex:
                    # Force creation of a new document if retrieving the document fails
                    logger.warning(f"Failed to retrieve the document; trying to create a new one: {str(doc_ex)}")
                    try:
                        # Close all open documents
                        for i in range(self.app.Documents.Count):
                            try:
                                self.app.Documents.Item(0).Close(False)  # Do not save
                            except:
                                pass
                        
                        # Create a new document.
                        self.doc = self.app.Documents.Add()
                    except Exception as new_doc_ex:
                        logger.error(f"Failed to create a new document: {str(new_doc_ex)}")
                        raise
                    
            except Exception as app_ex:
                # Start a new instance if the connection fails.
                logger.info(f"Connection failed; starting a new CAD instance: {str(app_ex)}")
                try:
                    # Start the application that matches the configured CAD type
                    app_id = "AutoCAD.Application"
                    app_name = "AutoCAD"
                    
                    if self.cad_type.lower() == "autocad":
                        app_id = "AutoCAD.Application"
                        app_name = "AutoCAD"
                    elif self.cad_type.lower() == "gcad":
                        app_id = "GCAD.Application"
                        app_name = "GstarCAD"
                    elif self.cad_type.lower() == "gstarcad":
                        app_id = "GCAD.Application"
                        app_name = "GstarCAD"
                    elif self.cad_type.lower() == "zwcad":
                        app_id = "ZWCAD.Application"
                        app_name = "ZWCAD"
                    
                    logger.info(f"Starting {app_name} instance...")
                    self.app = win32com.client.Dispatch(app_id)
                    self.app.Visible = True
                    
                    # Wait for CAD to start
                    time.sleep(self.startup_wait_time)  # Use the configured wait time
                    
                    # Create a new document.
                    logger.info("Trying to create a new document...")
                    # self.doc = self.app.Documents.Add()
                    self.doc = self.app.ActiveDocument
                except Exception as new_app_ex:
                    logger.error(f"Failed to start a new CAD instance: {str(new_app_ex)}")
                    raise
            
            # Perform an additional safety check and wait
            time.sleep(2)  # Give CAD more time to create the document
            
            if self.doc is None:
                raise Exception("Could not obtain a valid Document object")
            
            # Read a document property to verify that it is valid
            try:
                name = self.doc.Name
                logger.info(f"Document name: {name}")
            except Exception as name_ex:
                logger.error(f"Could not read the document name: {str(name_ex)}")
                raise Exception("The document object is invalid")
            
            logger.info("CAD started and is ready")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start CAD: {str(e)}")
            return False
        finally:
            # Clean up the previous instance.
            if old_app is not None:
                try:
                    del old_app
                except:
                    pass
    
        
    def is_running(self) -> bool:
        """Check whether CAD is running"""
        return self.app is not None and self.doc is not None
    
    def save_drawing(self, file_path: str) -> bool:
        """Save the current drawing to the specified path"""
        if not self.is_running():
            logger.error("CAD is not running; cannot save the drawing")
            return False
            
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Save the file
            self.doc.SaveAs(file_path)
            logger.info(f"Drawing saved to: {file_path}")
           
            return True
        except Exception as e:
            logger.error(f"Failed to save the drawing: {str(e)}")
            return False
    
    def refresh_view(self) -> None:
        """Refresh the CAD view"""
        if self.is_running():
            try:
                self.doc.Regen(1)  # acAllViewports = 1
            except Exception as e:
                logger.error(f"Failed to refresh the view: {str(e)}")
    
    def validate_lineweight(self, lineweight) -> int:
        """Validate and return a valid lineweight
        
        Return the default value 0 if the supplied lineweight is not valid
        
        Args:
            lineweight: The lineweight to validate
            
        Returns:
            A valid lineweight value
        """
        if lineweight is None:
            return None
            
        # Check whether the lineweight is in the list of valid values
        if lineweight in self.valid_lineweights:
            return lineweight
        else:
            logger.warning(f"Lineweight value {lineweight} is invalid; using the default value 0")
            return 0

    ################################################
    def rename_blocks(self, prefix="Block", filter_layer=None, filter_block_name_prefix=None):
        """Rename blocks by given prefix, with optional filters"""
        try:
            block_table = self.doc.Blocks
            count = 1

            for block in block_table:
                if block.IsLayout or block.Name.startswith("*"):
                    continue

                # Filter by block name prefix if specified
                if filter_block_name_prefix and not block.Name.startswith(filter_block_name_prefix):
                    continue

                # Filter by layer if specified (check all entities in block)
                if filter_layer:
                    has_layer = any(entity.Layer == filter_layer for entity in block)
                    if not has_layer:
                        continue

                new_name = f"{prefix}-{count}"
                self.doc.Blocks.Item(block.Name).Name = new_name
                count += 1

            self.refresh_view()
            return True

        except Exception as e:
            logger.error(f"Error renaming blocks: {e}")
            return False
    ################################################

    def draw_line(self, start_point: Tuple[float, float, float], 
                 end_point: Tuple[float, float, float], layer: str = None, color: int = None, lineweight=None) -> bool:
        """Draw a line"""
        if not self.is_running():
            return False
            
        try:
            # Ensure the point has three coordinates
            if len(start_point) == 2:
                start_point = (start_point[0], start_point[1], 0)
            if len(end_point) == 2:
                end_point = (end_point[0], end_point[1], 0)
      
            # Wrap the point coordinates in a VARIANT
            start_array = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, 
                                               [start_point[0], start_point[1], start_point[2]])
            end_array = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, 
                                             [end_point[0], end_point[1], end_point[2]])
            
            # Add the line
            line = self.doc.ModelSpace.AddLine(start_array, end_array)
            
            # Set the layer if one was specified
            if layer:
                # Ensure the layer exists
                self.create_layer(layer)
                # Set the entity layer
                line.Layer = layer
         
            # Set the color if one was specified
            if color is not None:
                line.Color = color

            if lineweight is not None:
                line.LineWeight = self.validate_lineweight(lineweight)
            
            # Refresh the view
            self.refresh_view()

            logger.debug(f"Drew line: start={start_point}; end={end_point}; layer={layer if layer else 'default'}; color={color if color is not None else 'default'}")
            return line
            
        except Exception as e:
            logger.error(f"Error drawing line: {str(e)}")
            return None
    
    def draw_circle(self, center: Tuple[float, float, float], 
                   radius: float, layer: str = None, color: int = None, lineweight=None) -> Any:
        """Draw a circle"""
        if not self.is_running():
            return None
            
        try:
            # Ensure the point has three coordinates
            if len(center) == 2:
                center = (center[0], center[1], 0)
            
            # Wrap the point coordinates in a VARIANT
            center_array = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, 
                                               [center[0], center[1], center[2]])
            
            # Add the circle
            circle = self.doc.ModelSpace.AddCircle(center_array, radius)
            
            # Set the layer if one was specified
            if layer:
                # Ensure the layer exists
                self.create_layer(layer)
                # Set the entity layer
                circle.Layer = layer
            
            # Set the color if one was specified
            if color is not None:
                circle.Color = color

            if lineweight is not None:
                circle.LineWeight = self.validate_lineweight(lineweight)
            
            # Refresh the view
            self.refresh_view()
            
            logger.debug(f"Drew circle: center={center}; radius={radius}; layer={layer if layer else 'default'}; color={color if color is not None else 'default'}")
            return circle
            
        except Exception as e:
            logger.error(f"Error drawing circle: {str(e)}")
            return None
    
    def draw_arc(self, center: Tuple[float, float, float], 
                radius: float, start_angle: float, end_angle: float, layer: str = None, color: int = None, lineweight=None) -> Any:
        """Draw an arc."""
        if not self.is_running():
            return None
            
        try:
            # Ensure the point has three coordinates
            if len(center) == 2:
                center = (center[0], center[1], 0)
                
            # Convert the angles to radians
            start_rad = math.radians(start_angle)
            end_rad = math.radians(end_angle)
            
            # Wrap the point coordinates in a VARIANT
            center_array = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, 
                                               [center[0], center[1], center[2]])
            
            # Add the arc.
            arc = self.doc.ModelSpace.AddArc(center_array, radius, start_rad, end_rad)
            
            # Set the layer if one was specified
            if layer:
                # Ensure the layer exists
                self.create_layer(layer)
                # Set the entity layer
                arc.Layer = layer
            
            # Set the color if one was specified
            if color is not None:
                arc.Color = color

            if lineweight is not None:
                arc.LineWeight = self.validate_lineweight(lineweight)
            
            # Refresh the view
            self.refresh_view()
            
            logger.debug(f"Drew arc: center={center}; radius={radius}; start angle={start_angle}; end angle={end_angle}; layer={layer if layer else 'default'}; color={color if color is not None else 'default'}")
            return arc
        except Exception as e:
            logger.error(f"Failed to draw arc: {str(e)}")
            return None
 
    def draw_ellipse(self, center: Tuple[float, float, float], 
                    major_axis: float, minor_axis: float, rotation: float = 0, 
                    layer: str = None, color: int = None, lineweight=None) -> Any:
        """Draw an ellipse"""
        if not self.is_running():
            return None
            
        try:
            # Ensure the point has three coordinates
            if len(center) == 2:
                center = (center[0], center[1], 0)
            
            if rotation is None:
                rotation = 0

            # Convert the rotation angle to radians
            rotation_rad = math.radians(rotation)
            
            # Wrap the point coordinates in a VARIANT
            center_array = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, 
                                               [center[0], center[1], center[2]])
            
            # Calculate the ellipse major-axis vector
            major_x = major_axis * math.cos(rotation_rad)
            major_y = major_axis * math.sin(rotation_rad)
            major_vector = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, 
                                               [major_x, major_y, 0])
            
            # Add the ellipse
            ellipse = self.doc.ModelSpace.AddEllipse(center_array, major_vector, minor_axis / major_axis)
            
            # Set the layer if one was specified
            if layer:
                # Ensure the layer exists
                self.create_layer(layer)
                # Set the entity layer
                ellipse.Layer = layer
            
            # Set the color if one was specified
            if color is not None:
                ellipse.Color = color

            if lineweight is not None:
                ellipse.LineWeight = self.validate_lineweight(lineweight)
            
            # Refresh the view
            self.refresh_view()
            
            logger.debug(f"Drew ellipse: center={center}; major axis={major_axis}; minor axis={minor_axis}; rotation={rotation}; layer={layer if layer else 'default'}; color={color if color is not None else 'default'}")
            return ellipse
        except Exception as e:
            logger.error(f"Failed to draw ellipse: {str(e)}")
            return None
    
    def draw_polyline(self, points: List[Tuple[float, float, float]], closed: bool = False, layer: str = None, color: int = None, lineweight=None) -> Any:
        """Draw a polyline."""
        if not self.is_running():
            return None
            
        try:
            # Ensure all points have three coordinates
            processed_points = []
            for point in points:
                if len(point) == 2:
                    processed_points.append((point[0], point[1], 0))
                else:
                    processed_points.append(point)

            # Closed polylines connect the last vertex to the first automatically.
            # Remove an explicitly repeated endpoint to avoid a redundant vertex.
            if closed and len(processed_points) > 1 and processed_points[-1] == processed_points[0]:
                processed_points.pop()

            # Lightweight polylines use 2D OCS vertex coordinates. Keep the
            # shared Z value as the entity elevation.
            elevations = [point[2] for point in processed_points]
            if any(z != elevations[0] for z in elevations[1:]):
                raise ValueError("A lightweight polyline requires all vertices to share the same Z elevation")
            point_array = win32com.client.VARIANT(
                pythoncom.VT_ARRAY | pythoncom.VT_R8,
                [coord for point in processed_points for coord in point[:2]],
            )

            # Add a 2D lightweight polyline.
            polyline = self.doc.ModelSpace.AddLightWeightPolyline(point_array)
            polyline.Elevation = elevations[0]
            
            # Close the polyline if requested
            if closed and len(processed_points) > 2:
                polyline.Closed = True
            
            # Set the layer if one was specified
            if layer:
                # Ensure the layer exists
                self.create_layer(layer)
                # Set the entity layer
                polyline.Layer = layer
            
            # Set the color if one was specified
            if color is not None:
                polyline.Color = color

            if lineweight is not None:
                polyline.LineWeight = self.validate_lineweight(lineweight)
            
            # Refresh the view
            self.refresh_view()

            logger.debug(f"Drew polyline with {len(points)} points, {'closed' if closed else 'open'}; layer={layer if layer else 'default'}; color={color if color is not None else 'default'}")
            return polyline
        except Exception as e:
            logger.error(f"Error drawing polyline: {str(e)}")
            return None
    
    def draw_rectangle(self, corner1: Tuple[float, float, float], 
                      corner2: Tuple[float, float, float], layer: str = None, color: int = None, lineweight=None) -> Any:
        """Draw a rectangle"""
        if not self.is_running():
            return None
            
        try:
            # Ensure the point has three coordinates
            if len(corner1) == 2:
                corner1 = (corner1[0], corner1[1], 0)
            if len(corner2) == 2:
                corner2 = (corner2[0], corner2[1], 0)
                
            # Calculate the four rectangle corners
            x1, y1, z1 = corner1
            x2, y2, z2 = corner2
            
            # Create the four rectangle corners.
            points = [
                (x1, y1, z1),
                (x2, y1, z1),
                (x2, y2, z1),
                (x1, y2, z1)
            ]
            
            # Draw the rectangle as a polyline.
            return self.draw_polyline(points, True, layer, color, lineweight)
        except Exception as e:
            logger.error(f"Error drawing rectangle: {str(e)}")
            return None
    
    def draw_text(self, position: Tuple[float, float, float], 
                 text: str, height: float = 2.5, rotation: float = 0, layer: str = None, color: int = None) -> Any:
        """Add text"""
        if not self.is_running():
            return None
            
        try:
            # Ensure the point has three coordinates
            if len(position) == 2:
                position = (position[0], position[1], 0)
            
            # Wrap the point coordinates in a VARIANT
            position_array = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, 
                                                 [position[0], position[1], position[2]])
                
            # Add text
            text_obj = self.doc.ModelSpace.AddText(text, position_array, height)
            
            # Set the rotation angle
            if rotation != 0:
                text_obj.Rotation = math.radians(rotation)
            
            # Set the layer if one was specified
            if layer:
                # Ensure the layer exists
                self.create_layer(layer)
                # Set the entity layer
                text_obj.Layer = layer
            
            # Set the color if one was specified
            if color is not None:
                text_obj.Color = color
            
            # Refresh the view
            self.refresh_view()
                                
            logger.debug(f"Added text '{text}'; position={position}; height={height}; rotation={rotation} degrees; layer={layer if layer else 'default'}; color={color if color is not None else 'default'}")
            return text_obj
        except Exception as e:
            logger.error(f"Error adding text: {str(e)}")
            return None
    
    def draw_hatch(self, points: List[Tuple[float, float, float]], 
                  pattern_name: str = "SOLID", scale: float = 1.0, layer: str = None, color: int = None) -> Any:
        """Draw a hatch pattern
        
        Args:
            points: Boundary points, each a 2D or 3D coordinate tuple.
            pattern_name: Hatch pattern name; defaults to "SOLID" (solid fill).
            scale: Hatch pattern scale; defaults to 1.0.
            layer: Layer name; uses the current layer when None
            color: Color index; uses the default color when None.
            
        Returns:
            Returns the hatch object on success, or None on failure
        """
        if not self.is_running():
            return None
            
        try:
            # Ensure all points are valid.
            if not points or len(points) < 3:
                logger.error("Failed to create hatch: at least 3 points are required to define the boundary")
                return None
                
            # Create a closed polyline as the boundary.
            closed_polyline = self.draw_polyline(points, closed=True, layer=layer)
            if not closed_polyline:
                logger.error("Failed to create hatch: could not create the boundary polyline")
                return None
                
            # Create the hatch object (0 means normal fill; True associates the boundary)
            hatch = self.doc.ModelSpace.AddHatch(0, pattern_name, True)
                
            # Add the outer boundary loop
            # Wrap the object array in a VARIANT
            object_ids = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [closed_polyline])
            hatch.AppendOuterLoop(object_ids)
                
            # Set the hatch pattern scale
            hatch.PatternScale = scale
                
            # Set the layer if one was specified
            if layer:
                # Ensure the layer exists
                self.create_layer(layer)
                # Set the entity layer
                hatch.Layer = layer
                
            # Set the color if one was specified
            if color is not None:
                hatch.Color = color
                                
            # Update the hatch (calculate the filled area)
            hatch.Evaluate()
            
            # Refresh the view
            self.refresh_view()
                
            logger.debug(f"Created hatch: pattern={pattern_name}; scale={scale}; layer={layer if layer else 'default'}; color={color if color is not None else 'default'}")
            return hatch
        except Exception as e:
            logger.error(f"Error creating hatch: {str(e)}")
            return None
    
    def zoom_extents(self) -> bool:
        """Zoom the view to show all objects"""
        if not self.is_running():
            return False
            
        try:
            self.doc.ActiveViewport.ZoomExtents()
            logger.info("Zoomed the view to show all objects")
            return True
        except Exception as e:
            logger.error(f"Error zooming the view: {str(e)}")
            return False
    
    def close(self) -> None:
        """Close the CAD controller"""
        try:
            # Release COM resources
            if self.app is not None:
                del self.app
            pythoncom.CoUninitialize()
        except:
            pass

    
    def create_layer(self, layer_name: str) -> bool:    # , color: Union[int, Tuple[int, int, int]] = 7
        """Create a new layer
        
        Args:
            layer_name: Layer name
            color: Color value: a CAD color index (int) or RGB value (tuple)
            
        Returns:
            Whether the operation succeeded
        """
        if not self.is_running():
            return False
        
        try:
            # Check whether the layer already exists
            for i in range(self.doc.Layers.Count):
                if self.doc.Layers.Item(i).Name == layer_name:
                    # The layer already exists; activate it
                    self.doc.ActiveLayer = self.doc.Layers.Item(i)
                    return True
                
            # Create a new layer
            new_layer = self.doc.Layers.Add(layer_name)
            
            # Do not set the layer color; set the color on its entities
            # # Set the color
            # if isinstance(color, int):
            #     # Use a color index
            #     new_layer.Color = color
            # elif isinstance(color, tuple) and len(color) == 3:
            #     # Use an RGB value
            #     r, g, b = color
            #     # Set TrueColor
            #     new_layer.TrueColor = self._create_true_color(r, g, b)
            
            # Set as the current layer
            self.doc.ActiveLayer = new_layer
            logger.info(f"Created new layer: {layer_name}")  # Color: {color}
            return True
        except Exception as e:
            logger.error(f"Error creating layer: {str(e)}")
            return False

    def add_dimension(self, start_point: Tuple[float, float, float], 
                     end_point: Tuple[float, float, float],
                     text_position: Tuple[float, float, float] = None, textheight: float = 5,layer: str = None, color: int=None) -> Any:
            """Add a linear dimension"""
            if not self.is_running():
                return None
            
            try:
                # Ensure the point has three coordinates
                if len(start_point) == 2:
                    start_point = (start_point[0], start_point[1], 0)
                if len(end_point) == 2:
                    end_point = (end_point[0], end_point[1], 0)
                
                # Calculate the text position automatically if none was provided
                if text_position is None:
                    # Above the midpoint between the start and end points
                    mid_x = (start_point[0] + end_point[0]) / 2
                    mid_y = (start_point[1] + end_point[1]) / 2
                    text_position = (mid_x, mid_y + 5, 0)
                elif len(text_position) == 2:
                    text_position = (text_position[0], text_position[1], 0)
                
                # Wrap the point coordinates in a VARIANT
                start_array = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, 
                                                 [start_point[0], start_point[1], start_point[2]])
                end_array = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, 
                                               [end_point[0], end_point[1], end_point[2]])
                text_pos_array = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, 
                                                     [text_position[0], text_position[1], text_position[2]])
                
                # Add the aligned dimension
                dimension = self.doc.ModelSpace.AddDimAligned(start_array, end_array, text_pos_array)
                
                # Set the text height.
                if textheight is not None:
                    dimension.TextHeight = textheight
                
                # Set the layer if one was specified
                if layer:
                    # Ensure the layer exists
                    self.create_layer(layer)
                    # Set the entity layer
                    dimension.Layer = layer

                # Set the color if one was specified
                if color is not None:
                    dimension.Color = color
                
                # Refresh the view
                self.refresh_view()

                logger.info(f"Added dimension from {start_point} to {end_point}; layer={layer if layer else 'default'}")
                return dimension
            except Exception as e:
                logger.error(f"Error adding dimension: {str(e)}")
                return None

