# -*- coding: utf-8 -*-
"""

Module containing the primary class used to build 
composite HOD models from a set of components. 

"""

__all__ = ['HodModel']

import numpy as np
import occupation_helpers as occuhelp
import defaults

class HodModel(object):
    """ Composite HOD model object. 
    The primary methods are for assigning the mean occupation of a galaxy population 
    to a halo, the intra-halo radial profile of that population, and the 
    accompanying methods to generate Monte Carlo realizations of those methods. 

    All behavior is derived from external classes passed to the constructor via 
    model_blueprint, which serves as a set of instructions for how the 
    composite model is to be built from the components. 

    """

    def __init__(self, halo_prof_model, model_blueprint):
        """ The methods of this class derive their behavior from other, external classes, 
        passed in the form of the model_blueprint, a dictionary whose keys 
        are the galaxy types found in the halos, e.g., 'centrals', 'satellites', 'orphans', etc.
        The values of the model_blueprint are themselves dictionaries whose keys  
        specify the type of model being passed, e.g., 'occupation_model', and values 
        are instances of that type of model. The model_blueprint dictionary is built by 
        the hod_designer interface. The input halo_prof_model is an instance of the class 
        governing the assumed profile of the underlying halos. 

        """

        # Bind the model-building instructions to the composite model
        self.halo_prof_model = halo_prof_model
        self.model_blueprint = model_blueprint

        # Create attributes for galaxy types and their occupation bounds
        self.gal_types = self.model_blueprint.keys()
        self.occupation_bound = {}
        for gal_type in self.gal_types:
            self.occupation_bound[gal_type] = (
                self.model_blueprint[gal_type]['occupation_model'].occupation_bound)

        # Create strings used by the MC methods to access the appropriate columns of the 
        # halo table passed by the mock factory
        # Also create a dictionary for which gal_types, and which behaviors, 
        # are assembly-biased. 
        self._create_haloprop_keys()

        # In MCMC applications, the output_dict items define the 
        # parameter set explored by the likelihood engine. 
        # Changing the values of the parameters in param_dict 
        # will propagate to the behavior of the component models, 
        # though the param_dict attributes attached to the component model 
        # instances themselves will not be changed. 
        self.param_dict = (
            self.build_composite_param_dict(
                self.model_blueprint)
            )

        # The following dictionary provides example shapes of all galaxy 
        # attributes created by component models. Used by the mock factories 
        # to allocate ndarrays for the galaxy properties. 
        self._example_attr_dict, self._gal_type_example_attr_dict = (
            self.get_example_attr_dict()
            )

        # The following dictionary has values that are function objects 
        # used to calculate new halo properties from existing ones. 
        # Its keys will be used as the names of the newly created columns
        # This includes halo profile parameters such as 'NFWmodel_conc', 
        # and also any other halo properties used by the component models
        self.additional_haloprops = self.get_new_haloprop_dict()

        self.publications = self.build_publication_list(
            self.model_blueprint)

    def retrieve_relevant_haloprops(self, gal_type, component_key, 
        *args, **kwargs):
        """ Method returning the arrays that need to be passed 
        to a component model in order to access its behavior. 
        """

        if ( (occuhelp.aph_len(args) == 0) & ('mock_galaxies' in kwargs.keys()) ):
            # In this case, we were passed a full mock galaxy catalog as a keyword argument
            mock = kwargs['mock_galaxies']
            # each component model has a dictionary containing the keys of the 
            # halo catalog that the component model needs from the halo catalog
            haloprop_key_dict = self.model_blueprint[gal_type][component_key].haloprop_key_dict
            # All such dictionaries have a key indicating the primary halo property governing the behavior
            prim_haloprop_key = haloprop_key_dict['prim_haloprop_key']
            # We were passed the full mock, but this function call only pertains to the slice of 
            # the arrays that correspond to gal_type galaxies. 
            # We save time by having pre-computed the relevant slice. 
            gal_type_slice = mock._gal_type_indices[gal_type]
            prim_haloprop = getattr(mock, prim_haloprop_key)[gal_type_slice]
            # Now pack the prim_haloprop array into a 1-element list
            output_columns = [prim_haloprop]
            # If there is a secondary halo property used by this component model, 
            # repeat the above retrieval and extend the list. 
            if 'sec_haloprop_key' in haloprop_key_dict.keys():
                sec_haloprop_key = haloprop_key_dict['sec_haloprop_key']
                sec_haloprop = getattr(mock, sec_haloprop_key)[gal_type_slice]
                output_columns.extend([sec_haloprop])

            return output_columns

        elif ( (occuhelp.aph_len(args) > 0) & ('mock_galaxies' not in kwargs.keys()) ):
            # In this case, we were directly passed the relevant arrays
            return list(args)
        ###
        ### Now address the cases where we were passed insensible arguments
        elif ( (occuhelp.aph_len(args) == 0) & ('mock_galaxies' not in kwargs.keys()) ):
            raise SyntaxError("Neither an array of halo properties "
                " nor a mock galaxy population was passed")
        else:
            raise SyntaxError("Do not pass both an array of halo properties "
                " and a mock galaxy population - pick one")

    def mean_occupation(self,gal_type,*args, **kwargs):
        """ Method supplying the mean abundance of gal_type galaxies. 
        The behavior of this method is inherited from one of the component models. 
        """

        component_key = 'occupation_model'
        method_name = 'mean_occupation'

        output_occupation = self.retrieve_component_behavior(
            gal_type, component_key, method_name, *args, **kwargs)

        return output_occupation


    def mc_occupation(self,gal_type,*args, **kwargs):
        """ Method providing a Monte Carlo realization of the mean occupation.
        The behavior of this method is inherited from one of the component models.
        """

        component_key = 'occupation_model'
        method_name = 'mc_occupation'

        output_mc_realization = self.retrieve_component_behavior(
            gal_type, component_key, method_name, *args, **kwargs)

        return output_mc_realization
        
    def mean_profile_parameters(self,gal_type,*args, **kwargs):
        """ Method returning the mean value of the parameters governing the radial profile 
        of gal_type galaxies. 
        The behavior of this method is inherited from one of the component models.
        """

        profile_model = self.model_blueprint[gal_type]['profile_model']
        inherited_method = profile_model.mean_profile_parameters
        output_profiles = self.retrieve_component_behavior(inherited_method,args)

        return output_profiles

    def mc_coords(self,gal_type,*args, **kwargs):
        """ Method returning a Monte Carlo realization of the radial profile. 
        The behavior of this method is inherited from one of the component models.
        """

        profile_model = self.model_blueprint[gal_type]['profile_model']
        inherited_method = profile_model.mc_coords
        output_mc_realization = self.retrieve_component_behavior(inherited_method,args)

        return output_mc_realization


    def retrieve_component_behavior(self, gal_type, component_key, method_name, 
        *args, **kwargs):
        """ Wrapper method whose purpose is solely to call the component model methods 
        using the correct number of arguments. Purely for user convenience. 

        """

        # The behavior of mc_occupation is inherited by the component model 
        component_model_instance = self.model_blueprint[gal_type][component_key]
        inherited_method = getattr(component_model_instance, method_name)

        # Retrieve the appropriate columns from halo_table
        haloprop_list = self.retrieve_relevant_haloprops(
            gal_type, component_key, *args, **kwargs)
        # haloprop_list is a one- or two-element list of arrays of halo properties. 
        # Use the * syntax to unpack this list into a sequence of positional arguments. 
        output = inherited_method(*haloprop_list)

        return output
 

    def build_composite_param_dict(self,model_blueprint):
        """ Method to build a dictionary of parameters for the composite model 
        by retrieving all the parameters of the component models. 

        Parameters 
        ----------
        model_blueprint : dict 
            Dictionary passed to the HOD factory __init__ constructor 
            that is used to provide instructions for how to build a 
            composite model from a set of components. 

        Returns 
        -------
        output_dict : dict 
            Dictionary of all parameters used by all component models. 
        """

        output_dict = {}

        # Loop over all galaxy types in the composite model
        for gal_type_dict in model_blueprint.values():
            # For each galaxy type, loop over its features
            for model_instance in gal_type_dict.values():

                occuhelp.test_repeated_keys(
                    output_dict, model_instance.param_dict)

                output_dict = dict(
                    model_instance.param_dict.items() + 
                    output_dict.items()
                    )

        return output_dict

    def build_publication_list(self, model_blueprint):
        """ Method to build a list of publications 
        associated with each component model. 

        Parameters 
        ----------
        model_blueprint : dict 
            Dictionary passed to the HOD factory __init__ constructor 
            that is used to provide instructions for how to build a 
            composite model from a set of components. 

        Returns 
        -------
        pub_list : array_like 
        """
        pub_list = []

        # Loop over all galaxy types in the composite model
        for gal_type_dict in model_blueprint.values():
            # For each galaxy type, loop over its features
            for model_instance in gal_type_dict.values():
                pub_list.extend(model_instance.publications)

        return pub_list


    def _create_haloprop_keys(self):

        # Create attribute for primary halo property used by all component models
        # Forced to be the same property defining the underlying halo profile 
        # seen by all galaxy types 
        self.prim_haloprop_key = self.halo_prof_model.prim_haloprop_key

        # If any of the galaxy types have any assembly-biased component behavior, 
        # create a second attribute called sec_haloprop_key. 
        # Force the secondary halo property to be the same for all behaviors 
        # of all galaxy types. May wish to relax this requirement later. 
        sec_haloprop_key_dict = {}
        for gal_type in self.gal_types:
            temp_dict = {}
            for behavior_key, behavior_model in self.model_blueprint[gal_type].iteritems():
                if hasattr(behavior_model,'sec_haloprop_key'):
                    temp_dict[behavior_key] = behavior_model.sec_haloprop_key
            if len(set(temp_dict.values())) > 1:
                raise KeyError("If implementing assembly bias for a particular gal_type, "
                    "must use the same secondary halo property "
                    " for all behaviors of this galaxy type")
            elif len(set(temp_dict.values())) == 1:
                sec_haloprop_key_dict[gal_type] = temp_dict
        if len(set(sec_haloprop_key_dict.values())) > 1:
            raise KeyError("If implementing assembly bias in a composite model, "
                " must use same secondary halo property for all galaxy types")
        elif len(set(sec_haloprop_key_dict.values())) == 1:
            self.sec_haloprop_key = sec_haloprop_key_dict.values()[0]
            self.sec_haloprop_key_dict = sec_haloprop_key_dict


    def get_example_attr_dict(self):
        """ Loop over all features of all gal_types, and build a composite 
        dictionary providing the shape of each attribute added by each feature. 
        Information is used when the mock factory allocates memory for galaxies. 
        """

        composite_dict = {}
        component_dict = {}
        for gal_type in self.gal_types:

            temp_component_dict={}

            for behavior_key, behavior_model in self.model_blueprint[gal_type].iteritems():

                if hasattr(behavior_model, '_example_attr_dict'):
                    new_dict = behavior_model._example_attr_dict
                    intersection = set(new_dict) & set(composite_dict)
                    for duplicate_key in intersection:
                        shape1 = np.shape(new_dict[duplicate_key])
                        shape2 = np.shape(composite_dict[duplicate_key])
                        if shape1 != shape2:
                            raise TypeError("For component model feature %s "
                                "of gal_type %s, found problem with key %s "
                                " while building composite _example_attr_dict\n"
                                "This key appears in at least one other component model dict, "
                                "but the shapes of the two provided example "
                                "values do not agree" % (behavior_key, gal_type, duplicate_key) )
                    composite_dict = dict(composite_dict.items() + new_dict.items())
                    temp_component_dict = dict(temp_component_dict.items() + new_dict.items())

            component_dict[gal_type] = temp_component_dict

        return composite_dict, component_dict

    def get_new_haloprop_dict(self):
        """ Return a dictionary that can be used to create an additional set of 
        halo properties that the halo catalog may not have. The keys of this 
        dictionary will be new column names to attach to the halo catalog, the 
        values of this dictionary are function objects used to compute the 
        new columns from the existing ones. Classic example is computing an NFW 
        concentration by a model for the concentration-mass relation. 
        """

        # Begin with the dictionary used by halo profile models to 
        # assign profile parameters (e.g., concentration) to halos
        output_haloprop_dict = self.halo_prof_model.param_func_dict

        # Search all features of every gal_type for new halo properties that need to be computed
        for gal_type in self.gal_types:
            for behavior_key, behavior_model in self.model_blueprint[gal_type].iteritems():
                if hasattr(behavior_model, 'new_haloprop_dict'):
                    new_dict = behavior_model.new_haloprop_dict
                    # Now check to see if the new halo property has already been 
                    # included by some other component model feature
                    intersection = set(new_dict) & set(output_haloprop_dict)
                    if intersection != {}:
                        repeated_key = intersection.pop()
                        warnings.warn("Found duplication of new halo property %s "
                            "to calculate. Ignoring the version defined in %s feature"
                            " of %s galaxies" % (intersection, repeated_key, gal_type))
                    else:
                        output_haloprop_dict = dict(
                            output_haloprop_dict.items() + new_dict.items()
                            )


        return output_haloprop_dict































