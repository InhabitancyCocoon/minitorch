from dataclasses import dataclass
from typing import Any, Iterable, Tuple
from typing_extensions import Protocol

# ## Task 1.1
# Central Difference calculation


def central_difference(f: Any, *vals: Any, arg: int = 0, epsilon: float = 1e-6) -> Any:
    r"""
    Computes an approximation to the derivative of `f` with respect to one arg.

    See :doc:`derivative` or https://en.wikipedia.org/wiki/Finite_difference for more details.

    Args:
        f : arbitrary function from n-scalar args to one value
        *vals : n-float values $x_0 \ldots x_{n-1}$
        arg : the number $i$ of the arg to compute the derivative
        epsilon : a small constant

    Returns:
        An approximation of $f'_i(x_0, \ldots, x_{n-1})$
    """
    vals_x_i_plus_epsilon = list(vals)
    vals_x_i_plus_epsilon[arg] += epsilon
    vals_x_i_plus_epsilon = tuple(vals_x_i_plus_epsilon)
    f_x_plus_epsilon = f(*vals_x_i_plus_epsilon)

    vals_x_i_minus_epsilon = list(vals)
    vals_x_i_minus_epsilon[arg] -= epsilon
    vals_x_i_minus_epsilon = tuple(vals_x_i_minus_epsilon)
    f_x_minus_epsilon = f(*vals_x_i_minus_epsilon)

    return (f_x_plus_epsilon - f_x_minus_epsilon) / (2 * epsilon)


variable_count = 1


class Variable(Protocol):
    def accumulate_derivative(self, x: Any) -> None:
        pass

    @property
    def unique_id(self) -> int:
        pass

    def is_leaf(self) -> bool:
        pass

    def is_constant(self) -> bool:
        pass

    @property
    def parents(self) -> Iterable["Variable"]:
        pass

    def chain_rule(self, d_output: Any) -> Iterable[Tuple["Variable", Any]]:
        pass


def topological_sort(variable: Variable) -> Iterable[Variable]:
    """
    Computes the topological order of the computation graph.

    Args:
        variable: The right-most variable

    Returns:
        Non-constant Variables in topological order starting from the right.
    """
    s = []
    cur = variable
    s.append(cur)
    vis = set()
    topological_order = []
    while s:
        for pref in cur.parents:
            if pref.unique_id not in vis:
                s.append(pref)
        if cur == s[-1]:
            s.pop()
            topological_order.append(cur)
            vis.add(cur.unique_id)
        else:
            cur = s[-1]
    return topological_order


def backpropagate(variable: Variable, deriv: Any) -> None:
    """
    Runs backpropagation on the computation graph in order to
    compute derivatives for the leave nodes.

    Args:
        variable: The right-most variable
        deriv  : Its derivative that we want to propagate backward to the leaves.

    No return. Should write to its results to the derivative values of each leaf through `accumulate_derivative`.
    """
    if variable.is_leaf():
        variable.accumulate_derivative(deriv)
        return
    if not variable.is_constant():
        back = variable.chain_rule(d_output=deriv)
        for pref, dev in back:
            backpropagate(pref, dev)


@dataclass
class Context:
    """
    Context class is used by `Function` to store information during the forward pass.
    """

    no_grad: bool = False
    saved_values: Tuple[Any, ...] = ()

    def save_for_backward(self, *values: Any) -> None:
        "Store the given `values` if they need to be used during backpropagation."
        if self.no_grad:
            return
        self.saved_values = values

    @property
    def saved_tensors(self) -> Tuple[Any, ...]:
        return self.saved_values
