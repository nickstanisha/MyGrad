from ..operations.operation_base import Operation
import numpy as np

__all__ = ["MaxMin"]


class MaxMin(Operation):
    def __call__(self, a, axis=None, keepdims=False, maxmin=None):
        """ Return the maximum (minimum) of a tensor, or along its axes.

            Parameters
            ----------
            a : pygrad.Tensor
                Input data.

            axis : Optional[int, Tuple[int, ...]]
                Axis or axes along which to operate. By default, flattened input is used.

            keepdims : bool, optional
                If this is set to True, the axes which are reduced are left
                in the result as dimensions with size one. With this option,
                the result will broadcast correctly against the original `arr`.

            maxmin : str
                'max' or 'min'. Selects the operation that is performed

            Returns
            -------
            amax : ndarray
                Maximum (minimum) of `a`. If `axis` is None, the result is a 0-D array."""
        assert maxmin in ("max", "min"), "Invalid keyword argument"
        op = np.argmax if maxmin == "max" else np.argmin

        # let numpy handle error checking
        np.amax(np.empty([1 for i in range(a.ndim)]), axis=axis, keepdims=keepdims)

        if a.ndim == 0:
            return a.data

        if hasattr(axis, '__iter__'):
            assert isinstance(axis, tuple)
            axis = tuple(ax % a.ndim for ax in axis)
            axis = None if len(axis) == a.ndim else tuple(sorted(axis))
        elif axis is not None:
            axis = (axis % a.ndim,)

        self.a = a
        self.axis = axis
        self.keepdims = keepdims

        # max(a) -> use argmax
        if self.axis is None:
            self.indices = np.unravel_index(op(a.data), a.shape)
            dat = a.data[self.indices]

        # max(x, axis=i) -> use argmax with specified axis
        elif len(self.axis) == 1:  #
            op_index = op(a.data, axis=self.axis[0])
            self.indices = list(np.indices(op_index.shape))
            self.indices.insert(self.axis[0], op_index)
            self.indices = tuple(self.indices)
            dat = a.data[self.indices]

        # max(x, axis=(i,j,...) ) -> Reshape data to use argmax along trailing axis
        else:
            self.static_ax = tuple(sorted(set(range(a.ndim)) - set(self.axis)))  # non-reduced axes (m, n, ..)
            self.to_trans = self.static_ax + self.axis  # (m, n, ..., i, j, ...)
            self.from_trans = tuple(np.argsort(self.to_trans))
            outshape = tuple(a.shape[i] for i in self.static_ax)

            z = a.data.transpose(*self.to_trans).reshape(*(outshape + (-1,)))  # (m, n, ..., i*j*[...])

            k = op(z, axis=-1)
            self.indices = tuple(i for i in np.indices(k.shape))
            self.indices += (k, )
            self.tmp_grad_shape = z.shape
            z = z[self.indices]

            dat = z.reshape(outshape)  # (m, n, ...)

        if not self.keepdims:
            return dat

        elif self.axis is None:
            keep_index = [np.newaxis for i in range(self.a.ndim)]
        else:
            keep_index = [slice(None) for i in range(self.a.ndim)]
            for i in self.axis:
                keep_index[i] = np.newaxis

        return np.asarray(dat)[keep_index]

    def backward_a(self, grad):

        if self.a.ndim == 0:
            self.a.backward(grad)

        # normalize shape of grad to be same as when keepdims=False
        if self.keepdims:
            if self.axis is not None:
                reduce = [slice(None) for i in range(self.a.ndim)]
                for i in self.axis:
                    reduce[i] = 0
            else:
                reduce = (0 for i in range(self.a.ndim))
            grad = grad[tuple(reduce)]

        # use argmax indices to broadcast grad to correct elements
        if self.axis is None or len(self.axis) == 1:
            out = np.zeros_like(self.a.data, dtype=float)
            out[self.indices] = grad
            self.a.backward(out)
        else:
            tmp = [slice(None) for i in range(self.a.ndim)]
            for i in self.axis:
                tmp[i] = np.newaxis

            out = np.zeros(self.tmp_grad_shape, dtype=float)
            out[self.indices] = grad
            shape = tuple(self.a.shape[i] for i in self.to_trans)
            self.a.backward(out.reshape(shape).transpose(*self.from_trans))
