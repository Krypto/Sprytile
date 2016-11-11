import bpy
import bgl
import blf
from math import floor
from bgl import *
from bpy_extras import view3d_utils
from mathutils import Vector, Matrix

class SprytileGui(bpy.types.Operator):
    bl_idname = "sprytile.gui_win"
    bl_label = "Sprytile GUI"

    # ================
    # Modal functions
    # ================
    @classmethod
    def poll(cls, context):
        return context.area.type == 'VIEW_3D'

    def modal(self, context, event):
        if context.scene.sprytile_data.is_running is False:
            SprytileGui.handler_remove(self, context)
            context.area.tag_redraw()
            return {'CANCELLED'}

        # Check if current_grid is different from current sprytile grid
        # if context.object.sprytile_gridid != SprytileGui.current_grid:
        #     # Setup the offscreen texture for the new grid
        #     setup_off_return = SprytileGui.setup_offscreen(self, context)
        #     if setup_off_return is not None:
        #         return setup_off_return
        #     # Skip redrawing on this frame
        #     return {'PASS_THROUGH'}

        self.gui_event = event
        context.area.tag_redraw()
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        if context.space_data.type == 'VIEW_3D':
            if context.scene.sprytile_data.is_running is False:
                return {'CANCELLED'}

            # # Try to setup offscreen
            setup_off_return = SprytileGui.setup_offscreen(self, context)
            if setup_off_return is not None:
                return setup_off_return

            SprytileGui.handler_add(self, context)
            if context.area:
                context.area.tag_redraw()
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            return {'CANCELLED'}

    # ==================
    # Actual GUI drawing
    # ==================
    @staticmethod
    def setup_offscreen(self, context):
        SprytileGui.offscreen = SprytileGui.setup_gpu_offscreen(self, context)
        if SprytileGui.offscreen:
            SprytileGui.texture = SprytileGui.offscreen.color_texture
        else:
            self.report({'ERROR'}, "Error initializing offscreen buffer. More details in the console")
            return {'CANCELLED'}
        return None

    @staticmethod
    def setup_gpu_offscreen(self, context):
        import gpu
        scene = context.scene
        object = context.object

        grid_id = object.sprytile_gridid

        # Get the current tile grid, to fetch the texture size to render to
        tilegrid = scene.sprytile_grids[grid_id]
        mat_idx = bpy.data.materials.find(tilegrid.mat_id)
        # Material wasn't found, abandon setup
        if mat_idx < 0:
            self.clear_offscreen()
            return None
        # look through the texture slots of the material
        # to find the first with a texture/image
        material = bpy.data.materials[mat_idx]
        target_img = None
        for texture_slot in material.texture_slots:
            if texture_slot is None:
                continue
            if texture_slot.texture is None:
                continue
            if texture_slot.texture.image is None:
                continue
            # Cannot use the texture slot image reference directly
            # Have to get it through bpy.data.images to be able to use with BGL
            target_img = bpy.data.images.get(texture_slot.texture.image.name)
            break
        # Couldn't get the texture outta here
        if target_img is None:
            SprytileGui.clear_offscreen(self)
            return None

        import gpu
        try:
            offscreen = gpu.offscreen.new(target_img.size[0], target_img.size[1])
        except Exception as e:
            print(e)
            SprytileGui.clear_offscreen(self)
            offscreen = None

        SprytileGui.texture_grid = target_img
        SprytileGui.current_grid = grid_id
        return offscreen

    @staticmethod
    def clear_offscreen(self):
        SprytileGui.texture = None

    @staticmethod
    def handler_add(self, context):
        SprytileGui.draw_callback = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_handler, (self, context), 'WINDOW', 'POST_PIXEL')

    @staticmethod
    def handler_remove(self, context):
        if SprytileGui.draw_callback is not None:
            bpy.types.SpaceView3D.draw_handler_remove(SprytileGui.draw_callback, 'WINDOW')
        SprytileGui.draw_callback = None

    @staticmethod
    def draw_callback_handler(self, context):
        """Callback handler"""
        # Handle UI interactions
        min, max = SprytileGui.handle_ui(self, context)

        SprytileGui.draw_offscreen(self, context)
        SprytileGui.draw_to_viewport(min, max)

    @staticmethod
    def handle_ui(self, context):

        event = self.gui_event

        region = context.region
        object = context.object

        tilegrid = context.scene.sprytile_grids[object.sprytile_gridid]

        texture = SprytileGui.texture_grid
        tex_size = Vector((texture.size[0], texture.size[1]))

        display_size = 200
        display_pad = 5
        min = Vector((region.width - (display_size + display_pad), display_pad))
        max = Vector((region.width - display_pad, (display_size + display_pad)))

        if event is None:
            return min, max

        if event.type in {'MOUSEMOVE'}:
            mouse_within_x = event.mouse_region_x >= min.x and event.mouse_region_x <= max.x
            mouse_within_y = event.mouse_region_y >= min.y and event.mouse_region_y <= max.y
            context.scene.sprytile_data.gui_use_mouse = mouse_within_x and mouse_within_y

        if context.scene.sprytile_data.gui_use_mouse is False:
            return min, max

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            click_pos = Vector((event.mouse_region_x - min.x, event.mouse_region_y - min.y))
            ratio_pos = Vector((click_pos.x / display_size, click_pos.y / display_size))
            tex_pos = Vector((ratio_pos.x * tex_size.x, ratio_pos.y * tex_size.y))
            # Inverse matrix tex_pos
            grid_pos = Vector((tex_pos.x / tilegrid.grid[0], tex_pos.y / tilegrid.grid[1]))
            grid_pos.x = floor(grid_pos.x)
            grid_pos.y = floor(grid_pos.y)
            tilegrid.tile_selection[0] = grid_pos.x
            tilegrid.tile_selection[1] = grid_pos.y
            print("%d, %d" % grid_pos[:])

        return min, max

    @staticmethod
    def draw_offscreen(self, context):
        """Draw the GUI into the offscreen texture"""
        offscreen = SprytileGui.offscreen
        target_img = SprytileGui.texture_grid
        size = Vector((target_img.size[0], target_img.size[1]))

        offscreen.bind()
        glDisable(GL_DEPTH_TEST)
        glMatrixMode (GL_PROJECTION);
        glLoadIdentity ();
        gluOrtho2D(0, size.x, 0, size.y)
        target_img.gl_load(0, bgl.GL_NEAREST, bgl.GL_NEAREST)
        glBindTexture(bgl.GL_TEXTURE_2D, target_img.bindcode[0])
        glTexParameteri(bgl.GL_TEXTURE_2D, bgl.GL_TEXTURE_MAG_FILTER, bgl.GL_NEAREST)
        glEnable(bgl.GL_TEXTURE_2D)
        glEnable(bgl.GL_BLEND)

        glColor4f(1.0, 1.0, 1.0, 1.0)
        glBegin(bgl.GL_QUADS)

        texco = [(0, 0), (0, 1), (1, 1), (1, 0)]
        verco = [(0, 0), (0, size.y), (size.x, size.y), (size.x, 0)]
        # first draw the texture
        for i in range(4):
            glTexCoord2f(texco[i][0], texco[i][1])
            glVertex2f(verco[i][0], verco[i][1])

        # Then draw other UI elements

        glEnd()
        offscreen.unbind()

    @staticmethod
    def draw_to_viewport(min, max):
        """Draw the offscreen texture into the viewport"""
        bgl.glBindTexture(bgl.GL_TEXTURE_2D, SprytileGui.texture)
        bgl.glTexParameteri(bgl.GL_TEXTURE_2D, bgl.GL_TEXTURE_MAG_FILTER, bgl.GL_NEAREST)
        bgl.glEnable(bgl.GL_TEXTURE_2D)
        bgl.glEnable(bgl.GL_BLEND)

        bgl.glColor4f(1.0, 1.0, 1.0, 1.0)
        bgl.glBegin(bgl.GL_QUADS)

        uv = [(0,0), (0,1), (1,1), (1,0)]
        vtx = [(min.x, min.y), (min.x, max.y), (max.x, max.y), (max.x, min.y)]
        for i in range(4):
            glTexCoord2f(uv[i][0],uv[i][1])
            glVertex2f(vtx[i][0],vtx[i][1])

        bgl.glEnd()

        # restore opengl defaults
        bgl.glLineWidth(1)
        bgl.glDisable(bgl.GL_BLEND)
        bgl.glDisable(bgl.GL_TEXTURE_2D)
        bgl.glColor4f(0.0, 0.0, 0.0, 1.0)

def register():
    bpy.utils.register_module(__name__)

def unregister():
    bpy.utils.unregister_module(__name__)

if __name__ == '__main__':
    register()