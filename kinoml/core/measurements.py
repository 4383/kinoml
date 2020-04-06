from typing import Union, Iterable, Any

from .conditions import AssayConditions
from .components import MolecularComponent


class BaseMeasurement:
    """
    We will have several subclasses depending on the experiment.
    They will also provide loss functions tailored to it.

    Parameters:
        value: The numeric measurement(s)
        conditions: Experimental conditions of this measurement
        components: Molecular entities measured
        strict: Whether to perform sanity checks at initialization.

    !!! todo
        Investigate possible uses for `pint`
    """

    def __init__(
        self,
        value: Union[float, Iterable[float]],
        conditions: AssayConditions,
        components: Iterable[MolecularComponent],
        strict: bool = True,
        **kwargs,
    ):
        self.value = value
        self.conditions = conditions
        # TODO: Do we want `components` here? It might introduce cyclic dependencies.
        self.components = components

        if strict:
            self.sanity_checks()

    def sanity_checks(self):
        """
        Perform some checks for valid values
        """


class PercentageDisplacementMeasurement(BaseMeasurement):

    """
    Measurement where the value must me a percentage of displacement.
    """

    def sanity_checks(self):
        super().sanity_checks()
        assert 0 <= self.value <= 100, f"Value `{self.value}` not in [0, 100]"

    def to_IC50(self):
        """
        Ideally, `self.conditions` should contain all we need to do
        the math here?
        """
        pass
