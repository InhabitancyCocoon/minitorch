from typing import Tuple

import numpy as np
from numba import njit, prange, jit

from .autodiff import Context
from .tensor import Tensor
from .tensor_data import (
    MAX_DIMS,
    Index,
    Shape,
    Strides,
    broadcast_index,
    index_to_position,
    OutIndex,
    to_index_by_strides
)
from .tensor_functions import Function

# This code will JIT compile fast versions your tensor_data functions.
# If you get an error, read the docs for NUMBA as to what is allowed
# in these functions.
to_index_by_strides = njit(inline="always")(to_index_by_strides)
index_to_position = njit(inline="always")(index_to_position)
broadcast_index = njit(inline="always")(broadcast_index)


@njit()
def to_index_by_strides(ordinal: int, strides: Strides, out_index: OutIndex):
    for idx in range(len(strides)):
        out_index[idx] = ordinal / strides[idx]
        ordinal %= strides[idx]


def _tensor_conv1d(
        out: Tensor,
        out_shape: Shape,
        out_strides: Strides,
        out_size: int,
        input: Tensor,
        input_shape: Shape,
        input_strides: Strides,
        weight: Tensor,
        weight_shape: Shape,
        weight_strides: Strides,
        reverse: bool,
) -> None:
    """
    1D Convolution implementation.

    Given input tensor of

       `batch, in_channels, width`

    and weight tensor

       `out_channels, in_channels, k_width`

    Computes padded output of

       `batch, out_channels, width`

    `reverse` decides if weight is anchored left (False) or right.
    (See diagrams)

    Args:
        out (Storage): storage for `out` tensor.
        out_shape (Shape): shape for `out` tensor.
        out_strides (Strides): strides for `out` tensor.
        out_size (int): size of the `out` tensor.
        input (Storage): storage for `input` tensor.
        input_shape (Shape): shape for `input` tensor.
        input_strides (Strides): strides for `input` tensor.
        weight (Storage): storage for `input` tensor.
        weight_shape (Shape): shape for `input` tensor.
        weight_strides (Strides): strides for `input` tensor.
        reverse (bool): anchor weight at left or right
    """
    batch_, out_channels, out_width = out_shape
    batch, in_channels, width = input_shape
    out_channels_, in_channels_, kw = weight_shape

    assert (
            batch == batch_
            and in_channels == in_channels_
            and out_channels == out_channels_
    )
    
    for out_pos in prange(out_size):
        out_index = np.empty_like(out_shape)
        to_index_by_strides(out_pos, out_strides, out_index)
        i, out_channel, j = out_index

        weight_index = np.empty_like(weight_shape)
        weight_index[0] = out_channel
        
        input_index = np.empty_like(input_shape)
        input_index[0] = i
    
        tmp = 0.

        for in_channel in range(in_channels):
            input_index[1] = in_channel
            weight_index[1] = in_channel

            for k in range(kw):
                input_index[2] = j + k if not reverse else j - k
                if input_index[2] < 0 or input_index[2] >= input_shape[2]:
                    continue
                weight_index[2] = k
                input_pos = index_to_position(input_index, input_strides)
                weight_pos = index_to_position(weight_index, weight_strides)
                tmp += input[input_pos] * weight[weight_pos]

        out[out_pos] = tmp


tensor_conv1d = _tensor_conv1d


class Conv1dFun(Function):
    @staticmethod
    def forward(ctx: Context, input: Tensor, weight: Tensor) -> Tensor:
        """
        Compute a 1D Convolution

        Args:
            ctx : Context
            input : batch x in_channel x h x w
            weight : out_channel x in_channel x kh x kw

        Returns:
            batch x out_channel x h x w
        """
        ctx.save_for_backward(input, weight)
        batch, in_channels, w = input.shape
        out_channels, in_channels2, kw = weight.shape
        assert in_channels == in_channels2

        # Run convolution
        output = input.zeros((batch, out_channels, w))
        tensor_conv1d(
            *output.tuple(), output.size, *input.tuple(), *weight.tuple(), False
        )
        return output

    @staticmethod
    def backward(ctx: Context, grad_output: Tensor) -> Tuple[Tensor, Tensor]:
        input, weight = ctx.saved_values
        batch, in_channels, w = input.shape
        out_channels, in_channels, kw = weight.shape
        grad_weight = grad_output.zeros((in_channels, out_channels, kw))
        new_input = input.permute(1, 0, 2)
        new_grad_output = grad_output.permute(1, 0, 2)
        tensor_conv1d(
            *grad_weight.tuple(),
            grad_weight.size,
            *new_input.tuple(),
            *new_grad_output.tuple(),
            False,
        )
        grad_weight = grad_weight.permute(1, 0, 2)

        grad_input = input.zeros((batch, in_channels, w))
        new_weight = weight.permute(1, 0, 2)
        tensor_conv1d(
            *grad_input.tuple(),
            grad_input.size,
            *grad_output.tuple(),
            *new_weight.tuple(),
            True,
        )
        return grad_input, grad_weight


conv1d = Conv1dFun.apply


def _tensor_conv2d(
        out: Tensor,
        out_shape: Shape,
        out_strides: Strides,
        out_size: int,
        input: Tensor,
        input_shape: Shape,
        input_strides: Strides,
        weight: Tensor,
        weight_shape: Shape,
        weight_strides: Strides,
        reverse: bool,
) -> None:
    """
    2D Convolution implementation.

    Given input tensor of

       `batch, in_channels, height, width`

    and weight tensor

       `out_channels, in_channels, k_height, k_width`

    Computes padded output of

       `batch, out_channels, height, width`

    `Reverse` decides if weight is anchored top-left (False) or bottom-right.
    (See diagrams)


    Args:
        out (Storage): storage for `out` tensor.
        out_shape (Shape): shape for `out` tensor.
        out_strides (Strides): strides for `out` tensor.
        out_size (int): size of the `out` tensor.
        input (Storage): storage for `input` tensor.
        input_shape (Shape): shape for `input` tensor.
        input_strides (Strides): strides for `input` tensor.
        weight (Storage): storage for `input` tensor.
        weight_shape (Shape): shape for `input` tensor.
        weight_strides (Strides): strides for `input` tensor.
        reverse (bool): anchor weight at top-left or bottom-right
    """
    batch_, out_channels, _, _ = out_shape
    batch, in_channels, height, width = input_shape
    out_channels_, in_channels_, kh, kw = weight_shape

    assert (
        batch == batch_
        and in_channels == in_channels_
        and out_channels == out_channels_
    )

    for out_pos in prange(out_size):
        out_index = np.empty_like(out_shape)
        to_index_by_strides(out_pos, out_strides, out_index)
        out_batch, out_channel, out_i, out_j = out_index
        for in_channel in range(in_channels):
            for weight_i in range(kh):
                input_i = out_i - weight_i if reverse else out_i + weight_i
                if input_i >= height or input_i < 0:
                    continue

                for weight_j in range(kw):
                    input_j = out_j - weight_j if reverse else out_j + weight_j
                    if input_j >= width or input_j < 0:
                        continue

                    weight_idx = out_channel * weight_strides[0] + in_channel * weight_strides[1] + \
                                 weight_i * weight_strides[2] + weight_j * weight_strides[3]
                    input_idx = out_batch * input_strides[0] + in_channel * input_strides[1] + \
                                input_i * input_strides[2] + input_j * input_strides[3]
                    
                    out[out_pos] += input[input_idx] * weight[weight_idx]

tensor_conv2d = njit(parallel=True, fastmath=True)(_tensor_conv2d)


class Conv2dFun(Function):
    @staticmethod
    def forward(ctx: Context, input: Tensor, weight: Tensor) -> Tensor:
        """
        Compute a 2D Convolution

        Args:
            ctx : Context
            input : batch x in_channel x h x w
            weight  : out_channel x in_channel x kh x kw

        Returns:
            (:class:`Tensor`) : batch x out_channel x h x w
        """
        ctx.save_for_backward(input, weight)
        batch, in_channels, h, w = input.shape
        out_channels, in_channels2, kh, kw = weight.shape
        assert in_channels == in_channels2
        output = input.zeros((batch, out_channels, h, w))
        tensor_conv2d(
            *output.tuple(), output.size, *input.tuple(), *weight.tuple(), False
        )
        return output

    @staticmethod
    def backward(ctx: Context, grad_output: Tensor) -> Tuple[Tensor, Tensor]:
        input, weight = ctx.saved_values
        batch, in_channels, h, w = input.shape
        out_channels, in_channels, kh, kw = weight.shape

        grad_weight = grad_output.zeros((in_channels, out_channels, kh, kw))
        new_input = input.permute(1, 0, 2, 3)
        new_grad_output = grad_output.permute(1, 0, 2, 3)
        tensor_conv2d(
            *grad_weight.tuple(),
            grad_weight.size,
            *new_input.tuple(),
            *new_grad_output.tuple(),
            False,
        )
        grad_weight = grad_weight.permute(1, 0, 2, 3)

        grad_input = input.zeros((batch, in_channels, h, w))
        new_weight = weight.permute(1, 0, 2, 3)
        tensor_conv2d(
            *grad_input.tuple(),
            grad_input.size,
            *grad_output.tuple(),
            *new_weight.tuple(),
            True,
        )
        return grad_input, grad_weight


conv2d = Conv2dFun.apply
