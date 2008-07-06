"""Manages a collection of module objects.  Also manages the lookup
tables.

"""
# Author: Prabhu Ramachandran <prabhu_r@users.sf.net>
# Copyright (c) 2005-2008,  Enthought, Inc.
# License: BSD Style.


import numpy

# Enthought library imports.
from enthought.traits.api import List, Instance, Trait, TraitPrefixList, \
                                 HasTraits, Str
from enthought.persistence.state_pickler import set_state

# Local imports
from enthought.mayavi.core.base import Base
from enthought.mayavi.core.module import Module
from enthought.mayavi.core.lut_manager import LUTManager
from enthought.mayavi.core.common import handle_children_state, exception


######################################################################
# `DataAttributes` class.
######################################################################
class DataAttributes(HasTraits):
    """A simple helper class used to store some attributes of an input
    data object."""

    # The version of this class.  Used for persistence.
    __version__ = 0

    # The name of the input data array.
    name = Str('')

    # The range of the data array.
    range = List

    def _get_np_arr(self, arr):
        data_array = arr.to_array()
        data_has_nan = numpy.isnan(data_array).any()
        return data_array, data_has_nan

    def compute_scalar(self, data, mode='point'):
        """Compute the scalar range from given VTK data array.  Mode
        can be 'point' or 'cell'."""
        if data is not None:
            if data.name is None or len(data.name) == 0:
                data.name = mode + '_scalars'
            self.name = data.name
            data_array, data_has_nan = self._get_np_arr(data)
            if data_has_nan:
                self.range = [float(numpy.nanmin(data_array)),
                              float(numpy.nanmax(data_array))]
            else:
                self.range = list(data.range)

    def compute_vector(self, data, type='point'):
        """Compute the vector range from given VTK data array.  Mode
        can be 'point' or 'cell'."""
        if data is not None:
            if data.name is None or len(data.name) == 0:
                data.name = mode + '_vectors'
            self.name = data.name
            data_array, data_has_nan = self._get_np_arr(data)
            if data_has_nan:
                d_mag = numpy.sqrt((data_array*data_array).sum(axis=1))
                self.range = [float(numpy.nanmin(d_mag)), 
                              float(numpy.nanmax(d_mag))]
            else:
                self.range = [0.0, data.max_norm]

    def config_lut(self, lut_mgr):
        """Set the attributes of the LUTManager."""
        rng = [0.0, 1.0]        
        if len(self.range) > 0:
            rng = self.range
            
        lut_mgr.default_data_range = list(rng)
        lut_mgr.default_data_name = self.name


# Constant for a ModuleManager class and it's View.
LUT_DATA_MODE_TYPES = ['auto', 'point data', 'cell data']

######################################################################
# `ModuleManager` class.
######################################################################
class ModuleManager(Base):

    # The source object this is connected to.
    source = Instance(Base)

    # The modules contained by this manager.
    children = List(Module)

    # The data type to use for the LUTs.  Changing this setting will
    # change the data range and name of the lookup table/legend bar.
    # If set to 'auto', it automatically looks for cell and point data
    # with point data being preferred over cell data and chooses the
    # one available.  If set to 'point data' it uses the input point
    # data for the LUT and if set to 'cell data' it uses the input
    # cell data.
    lut_data_mode = Trait('auto',
                          TraitPrefixList(LUT_DATA_MODE_TYPES),
                          desc='specify the data type used by the lookup tables',
                          )

    # The scalar lookup table manager.
    scalar_lut_manager = Instance(LUTManager, args=())
    
    # The vector lookup table manager.
    vector_lut_manager = Instance(LUTManager, args=())

    # The name of the ModuleManager.
    name = Str('Modules')

    # The icon
    icon = Str('modulemanager.ico')

    # The human-readable type for this object
    type = Str(' module manager')


    ######################################################################
    # `object` interface
    ######################################################################
    def __get_pure_state__(self):
        d = super(ModuleManager, self).__get_pure_state__()
        # Source is setup dynamically, don't pickle it.
        d.pop('source', None)
        return d

    def __set_pure_state__(self, state):
        # Do everything but our kids.
        set_state(self, state, ignore=['children'])
        # Setup children.
        handle_children_state(self.children, state.children)
        # Now setup the children.
        set_state(self, state, first=['children'], ignore=['*'])
        self.update()

    ######################################################################
    # `ModuleManager` interface
    ######################################################################
    def update(self):
        """Update any internal data.

        This is invoked when the source changes or when there are
        pipeline/data changes upstream.
        """
        self._setup_scalar_data()
        self._setup_vector_data()


    ######################################################################
    # `Base` interface
    ######################################################################
    def start(self):
        """This is invoked when this object is added to the mayavi
        pipeline.
        """
        # Do nothing if we are already running.
        if self.running:
            return
        
        # Setup event handlers.
        self._setup_event_handlers()

        # Start all our children.
        for obj in self.children:
            obj.start()
        for obj in (self.scalar_lut_manager, self.vector_lut_manager):
            obj.start()

        # Call parent method to set the running state.
        super(ModuleManager, self).start()

    def stop(self):
        """Invoked when this object is removed from the mayavi
        pipeline.
        """
        if not self.running:
            return

        # Teardown event handlers.
        self._teardown_event_handlers()

        # Stop all our children.
        for obj in self.children:
            obj.stop()
        for obj in (self.scalar_lut_manager, self.vector_lut_manager):
            obj.stop()
        
        # Call parent method to set the running state.
        super(ModuleManager, self).stop()

    def add_child(self, child):
        """This method intelligently adds a child to this object in
        the MayaVi pipeline.        
        """
        if isinstance(child, Module):
            self.children.append(child)
        else:
            # Ask our source to deal with it.
            self.source.add_child(child)

    ######################################################################
    # `TreeNodeObject` interface
    ######################################################################
    def tno_can_add(self, node, add_object):
        """ Returns whether a given object is droppable on the node.
        """
        try:
            if issubclass(add_object, Module):
                return True
        except TypeError:
            if isinstance(add_object, Module):
                return True
        return False

    def tno_drop_object(self, node, dropped_object):
        """ Returns a droppable version of a specified object.
        """
        if isinstance(dropped_object, Module):
            return dropped_object

    ######################################################################
    # Non-public interface
    ######################################################################
    def _children_changed(self, old, new):
        self._handle_children(old, new)

    def _children_items_changed(self, list_event):
        self._handle_children(list_event.removed, list_event.added)

    def _handle_children(self, removed, added):
        # Stop all the old children.
        for obj in removed:
            obj.stop()
        # Setup and start the new ones.
        for obj in added:
            obj.set(module_manager=self, scene=self.scene)
            if self.running:
                # It makes sense to start children only if we are running.
                # If not, the children will be started when we start.
                try:
                    obj.start()
                except:
                    exception()

    def _source_changed(self):
        self.update()
        
    def _setup_event_handlers(self):
        src = self.source
        src.on_trait_event(self.update, 'pipeline_changed')
        src.on_trait_event(self.update, 'data_changed')

    def _teardown_event_handlers(self):
        src = self.source
        src.on_trait_event(self.update, 'pipeline_changed', remove=True)
        src.on_trait_event(self.update, 'data_changed', remove=True)

    def _scene_changed(self, value):        
        for obj in self.children:
            obj.scene = value        
        for obj in (self.scalar_lut_manager, self.vector_lut_manager):
            obj.scene = value

    def _lut_data_mode_changed(self, value):
        self.update()

    def _setup_scalar_data(self):
        """Computes the scalar range and an appropriate name for the
        lookup table."""
        input = self.source.outputs[0]
        ps = input.point_data.scalars
        cs = input.cell_data.scalars

        data_attr = DataAttributes(name='No scalars')
        point_data_attr = DataAttributes(name='No scalars')
        point_data_attr.compute_scalar(ps, 'point')
        cell_data_attr = DataAttributes(name='No scalars')
        cell_data_attr.compute_scalar(cs, 'cell')
        
        if self.lut_data_mode == 'auto':
            if len(point_data_attr.range) > 0:
                data_attr.copy_traits(point_data_attr)
            elif len(cell_data_attr.range) > 0:
                data_attr.copy_traits(cell_data_attr)
        elif self.lut_data_mode == 'point data':
            data_attr.copy_traits(point_data_attr)
        elif self.lut_data_mode == 'cell data':
            data_attr.copy_traits(cell_data_attr)

        data_attr.config_lut(self.scalar_lut_manager)

    def _setup_vector_data(self):        
        input = self.source.outputs[0]
        pv = input.point_data.vectors
        cv = input.cell_data.vectors

        data_attr = DataAttributes(name='No vectors')
        point_data_attr = DataAttributes(name='No vectors')
        point_data_attr.compute_vector(pv, 'point')
        cell_data_attr = DataAttributes(name='No vectors')
        cell_data_attr.compute_vector(cv, 'cell')
        
        if self.lut_data_mode == 'auto':
            if len(point_data_attr.range) > 0:
                data_attr.copy_traits(point_data_attr)
            elif len(cell_data_attr.range) > 0:
                data_attr.copy_traits(cell_data_attr)
        elif self.lut_data_mode == 'point data':
            data_attr.copy_traits(point_data_attr)
        elif self.lut_data_mode == 'cell data':
            data_attr.copy_traits(cell_data_attr)

        data_attr.config_lut(self.vector_lut_manager)

    def _visible_changed(self,value):
        for c in self.children:
            c.visible = value
        self.scalar_lut_manager.visible = value
        self.vector_lut_manager.visible = value
    
        super(ModuleManager,self)._visible_changed(value)

    def __menu_helper_default(self):
        from enthought.mayavi.core.traits_menu import ModuleMenuHelper
        return ModuleMenuHelper(object=self)
