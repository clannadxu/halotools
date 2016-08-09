#!/usr/bin/env python
from __future__ import (absolute_import, division, print_function)

from unittest import TestCase
from astropy.tests.helper import pytest

import numpy as np
from copy import copy

from ...factories import HodModelFactory, PrebuiltHodModelFactory

from ....sim_manager import FakeSim
from ....empirical_models import zheng07_model_dictionary, OccupationComponent
from ....custom_exceptions import HalotoolsError

__all__ = ['TestHodModelFactory']


class TestHodModelFactory(TestCase):
    """ Class providing tests of the `~halotools.empirical_models.SubhaloModelFactory`.
    """

    def setUp(self):
        """ Pre-load various arrays into memory for use by all tests.
        """
        pass

    def test_empty_arguments(self):
        with pytest.raises(HalotoolsError) as err:
            model = HodModelFactory()
        substr = "You did not pass any model features to the factory"
        assert substr in err.value.args[0]

    def test_populate_mock1(self):
        model = PrebuiltHodModelFactory('zheng07')
        halocat = FakeSim()
        model.populate_mock(halocat)
        model.populate_mock(halocat=halocat)

    def test_Num_ptcl_requirement(self):
        """ Demonstrate that passing in varying values for
        Num_ptcl_requirement results in the proper behavior.
        """
        model = PrebuiltHodModelFactory('zheng07')
        halocat = FakeSim()
        actual_mvir_min = halocat.halo_table['halo_mvir'].min()

        model.populate_mock(halocat=halocat)
        default_mvir_min = model.mock.particle_mass*model.mock.Num_ptcl_requirement
        # verify that the cut was applied
        assert np.all(model.mock.halo_table['halo_mvir'] > default_mvir_min)
        # verify that the cut was non-trivial
        assert np.any(halocat.halo_table['halo_mvir'] < default_mvir_min)

        del model.mock
        model.populate_mock(halocat=halocat, Num_ptcl_requirement=0.)
        assert model.mock.Num_ptcl_requirement == 0.
        assert np.any(model.mock.halo_table['halo_mvir'] < default_mvir_min)

    def test_unavailable_haloprop(self):
        halocat = FakeSim()
        m = PrebuiltHodModelFactory('zheng07')
        m._haloprop_list.append("Jose Canseco")
        with pytest.raises(HalotoolsError) as err:
            m.populate_mock(halocat=halocat)
        substr = "this column is not available in the catalog you attempted to populate"
        assert substr in err.value.args[0]
        assert "``Jose Canseco``" in err.value.args[0]

    def test_unavailable_upid(self):
        halocat = FakeSim()
        del halocat.halo_table['halo_upid']
        m = PrebuiltHodModelFactory('zheng07')

        with pytest.raises(HalotoolsError) as err:
            m.populate_mock(halocat=halocat)
        substr = "does not have the ``halo_upid`` column."
        assert substr in err.value.args[0]

    def test_censat_consistency_check(self):
        """
        This test verifies that an informative exception will be raised if
        a satellite OccupationComponent implements the ``cenocc_model`` feature
        in a way that is inconsistent with the actual central occupation component
        used in the composite model.

        See https://github.com/astropy/halotools/issues/577 for context.
        """
        model = HodModelFactory(**zheng07_model_dictionary(modulate_with_cenocc=True))
        model._test_censat_occupation_consistency(model.model_dictionary)

        class DummySatComponent(OccupationComponent):
            def __init__(self):
                self.central_occupation_model = 43
                self.gal_type = 'satellites'

        model.model_dictionary['dummy_key'] = DummySatComponent()
        with pytest.raises(HalotoolsError) as err:
            model._test_censat_occupation_consistency(model.model_dictionary)
        substr = "has a ``central_occupation_model`` attribute with an inconsistent "
        assert substr in err.value.args[0]

    def tearDown(self):
        pass
