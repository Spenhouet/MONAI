# Copyright 2020 - 2021 MONAI Consortium
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Union

import numpy as np
import torch

from monai.config import NdarrayTensor
from monai.transforms import rescale_array
from monai.utils import optional_import

PIL, _ = optional_import("PIL")
GifImage, _ = optional_import("PIL.GifImagePlugin", name="Image")
SummaryX, _ = optional_import("tensorboardX.proto.summary_pb2", name="Summary")
SummaryWriterX, has_tensorboardx = optional_import("tensorboardX", name="SummaryWriter")

if TYPE_CHECKING:
    from tensorboard.compat.proto.summary_pb2 import Summary
    from torch.utils.tensorboard import SummaryWriter
else:
    Summary, _ = optional_import("tensorboard.compat.proto.summary_pb2", name="Summary")
    SummaryWriter, _ = optional_import("torch.utils.tensorboard", name="SummaryWriter")

__all__ = ["make_animated_gif_summary", "add_animated_gif", "add_animated_gif_no_channels", "plot_2d_or_3d_image"]


def _image3_animated_gif(tag: str, image: Union[np.ndarray, torch.Tensor], writer, scale_factor: float = 1.0):
    """Function to actually create the animated gif.

    Args:
        tag: Data identifier
        image: 3D image tensors expected to be in `HWD` format
        scale_factor: amount to multiply values by. if the image data is between 0 and 1, using 255 for this value will
            scale it to displayable range
    """
    if len(image.shape) != 3:
        raise AssertionError("3D image tensors expected to be in `HWD` format, len(image.shape) != 3")

    ims = [(np.asarray(image[:, :, i]) * scale_factor).astype(np.uint8) for i in range(image.shape[2])]
    ims = [GifImage.fromarray(im) for im in ims]
    img_str = b""
    for b_data in PIL.GifImagePlugin.getheader(ims[0])[0]:
        img_str += b_data
    img_str += b"\x21\xFF\x0B\x4E\x45\x54\x53\x43\x41\x50" b"\x45\x32\x2E\x30\x03\x01\x00\x00\x00"
    for i in ims:
        for b_data in PIL.GifImagePlugin.getdata(i):
            img_str += b_data
    img_str += b"\x3B"

    summary = SummaryX if has_tensorboardx and isinstance(writer, SummaryWriterX) else Summary
    summary_image_str = summary.Image(height=10, width=10, colorspace=1, encoded_image_string=img_str)
    image_summary = summary.Value(tag=tag, image=summary_image_str)
    return summary(value=[image_summary])


def make_animated_gif_summary(
    tag: str,
    image: Union[np.ndarray, torch.Tensor],
    writer=None,
    max_out: int = 3,
    animation_axes: Sequence[int] = (3,),
    image_axes: Sequence[int] = (1, 2),
    other_indices: Optional[Dict] = None,
    scale_factor: float = 1.0,
) -> Summary:
    """Creates an animated gif out of an image tensor in 'CHWD' format and returns Summary.

    Args:
        tag: Data identifier
        image: The image, expected to be in CHWD format
        writer: the tensorboard writer to plot image
        max_out: maximum number of image channels to animate through
        animation_axes: axis to animate on (not currently used)
        image_axes: axes of image (not currently used)
        other_indices: (not currently used)
        scale_factor: amount to multiply values by.
            if the image data is between 0 and 1, using 255 for this value will scale it to displayable range
    """

    suffix = "/image" if max_out == 1 else "/image/{}"
    if other_indices is None:
        other_indices = {}
    axis_order = [0] + list(animation_axes) + list(image_axes)

    slicing = []
    for i in range(len(image.shape)):
        if i in axis_order:
            slicing.append(slice(None))
        else:
            other_ind = other_indices.get(i, 0)
            slicing.append(slice(other_ind, other_ind + 1))
    image = image[tuple(slicing)]

    summary_op = []
    for it_i in range(min(max_out, list(image.shape)[0])):
        one_channel_img: Union[torch.Tensor, np.ndarray] = (
            image[it_i, :, :, :].squeeze(dim=0) if isinstance(image, torch.Tensor) else image[it_i, :, :, :]
        )
        summary_op.append(_image3_animated_gif(tag + suffix.format(it_i), one_channel_img, writer, scale_factor))
    return summary_op


def add_animated_gif(
    writer: SummaryWriter,
    tag: str,
    image_tensor: Union[np.ndarray, torch.Tensor],
    max_out: int = 3,
    scale_factor: float = 1.0,
    global_step: Optional[int] = None,
) -> None:
    """Creates an animated gif out of an image tensor in 'CHWD' format and writes it with SummaryWriter.

    Args:
        writer: Tensorboard SummaryWriter to write to
        tag: Data identifier
        image_tensor: tensor for the image to add, expected to be in CHWD format
        max_out: maximum number of image channels to animate through
        scale_factor: amount to multiply values by. If the image data is between 0 and 1, using 255 for this value will
            scale it to displayable range
        global_step: Global step value to record
    """
    summary = make_animated_gif_summary(
        tag=tag,
        image=image_tensor,
        writer=writer,
        max_out=max_out,
        animation_axes=[1],
        image_axes=[2, 3],
        scale_factor=scale_factor,
    )
    for s in summary:
        # add GIF for every channel separately
        writer._get_file_writer().add_summary(s, global_step)


def add_animated_gif_no_channels(
    writer: SummaryWriter,
    tag: str,
    image_tensor: Union[np.ndarray, torch.Tensor],
    max_out: int = 3,
    scale_factor: float = 1.0,
    global_step: Optional[int] = None,
) -> None:
    """Creates an animated gif out of an image tensor in 'HWD' format that does not have
    a channel dimension and writes it with SummaryWriter. This is similar to the "add_animated_gif"
    after inserting a channel dimension of 1.

    Args:
        writer: Tensorboard SummaryWriter to write to
        tag: Data identifier
        image_tensor: tensor for the image to add, expected to be in HWD format
        max_out: maximum number of image channels to animate through
        scale_factor: amount to multiply values by. If the image data is between 0 and 1,
                              using 255 for this value will scale it to displayable range
        global_step: Global step value to record
    """
    writer._get_file_writer().add_summary(
        make_animated_gif_summary(
            tag=tag,
            image=image_tensor,
            writer=writer,
            max_out=max_out,
            animation_axes=[1],
            image_axes=[1, 2],
            scale_factor=scale_factor,
        )[0],
        global_step,
    )


def plot_2d_or_3d_image(
    data: Union[NdarrayTensor, List[NdarrayTensor]],
    step: int,
    writer: SummaryWriter,
    index: int = 0,
    max_channels: int = 1,
    max_frames: int = 24,
    tag: str = "output",
) -> None:
    """Plot 2D or 3D image on the TensorBoard, 3D image will be converted to GIF image.

    Note:
        Plot 3D or 2D image(with more than 3 channels) as separate images.
        And if writer is from TensorBoardX, data has 3 channels and `max_channels=3`, will plot as RGB video.

    Args:
        data: target data to be plotted as image on the TensorBoard.
            The data is expected to have 'NCHW[D]' dimensions or a list of data with `CHW[D]` dimensions,
            and only plot the first in the batch.
        step: current step to plot in a chart.
        writer: specify TensorBoard or TensorBoardX SummaryWriter to plot the image.
        index: plot which element in the input data batch, default is the first element.
        max_channels: number of channels to plot.
        max_frames: if plot 3D RGB image as video in TensorBoardX, set the FPS to `max_frames`.
        tag: tag of the plotted image on TensorBoard.
    """
    data_index = data[index]
    d: np.ndarray = data_index.detach().cpu().numpy() if isinstance(data_index, torch.Tensor) else data_index

    if d.ndim == 2:
        d = rescale_array(d, 0, 1)  # type: ignore
        dataformats = "HW"
        writer.add_image(f"{tag}_{dataformats}", d, step, dataformats=dataformats)
        return

    if d.ndim == 3:
        if d.shape[0] == 3 and max_channels == 3:  # RGB
            dataformats = "CHW"
            writer.add_image(f"{tag}_{dataformats}", d, step, dataformats=dataformats)
            return
        dataformats = "HW"
        for j, d2 in enumerate(d[:max_channels]):
            d2 = rescale_array(d2, 0, 1)
            writer.add_image(f"{tag}_{dataformats}_{j}", d2, step, dataformats=dataformats)
        return

    if d.ndim >= 4:
        spatial = d.shape[-3:]
        d = d.reshape([-1] + list(spatial))
        if d.shape[0] == 3 and max_channels == 3 and has_tensorboardx and isinstance(writer, SummaryWriterX):  # RGB
            writer.add_video(tag, d[None], step, fps=max_frames, dataformats="NCHWT")
            return
        # scale data to 0 - 255 for visualization
        max_channels = min(max_channels, d.shape[0])
        d = np.stack([rescale_array(i, 0, 255) for i in d[:max_channels]], axis=0)
        # will plot every channel as a separate GIF image
        add_animated_gif(writer, f"{tag}_HWD", d, max_out=max_channels, global_step=step)
        return
