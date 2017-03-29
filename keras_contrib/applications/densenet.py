# -*- coding: utf-8 -*-
"""DenseNet models for Keras.

# Reference

- [Densely Connected Convolutional Networks](https://arxiv.org/pdf/1608.06993.pdf)
- [The One Hundred Layers Tiramisu: Fully Convolutional DenseNets for Semantic Segmentation](https://arxiv.org/pdf/1611.09326.pdf)
"""
from __future__ import print_function
from __future__ import absolute_import
from __future__ import division

import warnings

from keras.models import Model
from keras.layers.core import Dense, Dropout, Activation, Reshape
from keras.layers.convolutional import Conv2D, Conv2DTranspose, UpSampling2D
from keras.layers.pooling import AveragePooling2D
from keras.layers.pooling import GlobalAveragePooling2D
from keras.layers import Input, merge
from keras.layers.merge import concatenate
from keras.layers.normalization import BatchNormalization
from keras.regularizers import l2
from keras.utils.layer_utils import convert_all_kernels_in_model
from keras.utils.data_utils import get_file
from keras.engine.topology import get_source_inputs
from keras.applications.imagenet_utils import _obtain_input_shape
import keras.backend as K

from keras_contrib.layers.convolutional import SubPixelUpscaling

TH_WEIGHTS_PATH = 'https://github.com/titu1994/DenseNet/releases/download/v2.0/DenseNet-40-12-Theano-Backend-TH-dim-ordering.h5'
TF_WEIGHTS_PATH = 'https://github.com/titu1994/DenseNet/releases/download/v2.0/DenseNet-40-12-Tensorflow-Backend-TF-dim-ordering.h5'
TH_WEIGHTS_PATH_NO_TOP = 'https://github.com/titu1994/DenseNet/releases/download/v2.0/DenseNet-40-12-Theano-Backend-TH-dim-ordering-no-top.h5'
TF_WEIGHTS_PATH_NO_TOP = 'https://github.com/titu1994/DenseNet/releases/download/v2.0/DenseNet-40-12-Tensorflow-Backend-TF-dim-ordering-no-top.h5'


def DenseNet(input_shape=None, depth=40, nb_dense_block=3, growth_rate=12,
             nb_filter=16,
             nb_layers_per_block=-1, bottleneck=False, reduction=0.0,
             dropout_rate=0.0, weight_decay=1E-4, include_top=True,
             top='classification',
             weights='cifar10', input_tensor=None,
             classes=10, transition_dilation_rate=1,
             transition_pooling="avg",
             transition_kernel_size=(1, 1),
             activation='softmax'):
    """Instantiate the DenseNet architecture,
        optionally loading weights pre-trained
        on CIFAR-10. Note that when using TensorFlow,
        for best performance you should set
        `image_dim_ordering="tf"` in your Keras config
        at ~/.keras/keras.json.

        The model and the weights are compatible with both
        TensorFlow and Theano. The dimension ordering
        convention used by the model is the one
        specified in your Keras config file.

        For segmentation problems specify `transition_dilation_rate >= 2`,
        `transition_pooling=None`, `weights=None`, `top='segmentation'`.
        Good options also include `nb_dense_block=4`, `nb_layers_per_block=4`,
        and `depth=None`, but this varies by application.

        # Arguments

            input_shape: optional shape tuple, only to be specified
                if `include_top` is False (otherwise the input shape
                has to be `(32, 32, 3)` (with `tf` dim ordering)
                or `(3, 32, 32)` (with `th` dim ordering).
                It should have exactly 3 inputs channels,
                and width and height should be no smaller than 8.
                E.g. `(200, 200, 3)` would be one valid value.
            depth: Number of layers in the DenseNet. May be None if
                nb_dense_block and nb_layers_per_block are set.
            nb_dense_block: number of dense blocks to add to end (generally = 3)
            growth_rate: number of filters to add per dense block
            nb_filter: initial number of filters. -1 indicates initial
                number of filters is 2 * growth_rate
            nb_layers_per_block: number of layers in each dense block.
                Can be a -1, positive integer or a list.
                If -1, calculates nb_layer_per_block from the network depth.
                If positive integer, a set number of layers per dense block.
                If list, nb_layer is used as provided. Note that list size must
                be (nb_dense_block + 1)
            bottleneck: flag to add bottleneck blocks in between dense blocks
            reduction: reduction factor of transition blocks.
                Note : reduction value is inverted to compute compression.
            dropout_rate: dropout rate
            weight_decay: weight decay factor
            include_top: whether to include the fully-connected
                layer at the top of the network.
            top: One of 'segmentation', 'classification', or None.
                'classification' includes global average pooling and
                a dense activation layer with a single output and multiple
                classes. 'segmentation' includes a Conv2D and
                a softmax activation. None is the same as `include_top=False`.
            weights: one of `None` (random initialization) or
                "cifar10" (pre-training on CIFAR-10)..
            input_tensor: optional Keras tensor
                (i.e. output of `layers.Input()`)
                to use as image input for the model.
            classes: optional number of classes to classify images
                into, only to be specified if `include_top` is True, and
                if no `weights` argument is specified.
            transition_dilation_rate: An integer or tuple/list of 2 integers,
                specifying the dilation rate to in transition blocks for
                dilated convolution, increasing the receptive field of the
                algorithm. Can be a single integer to specify the same value
                for all spatial dimensions.
            transition_pooling: Data pooling to reduce resolution in transition
                blocks, one of "avg", "max", or None.
            transition_kernel_size: Adjusts the filter size of the Conv2D in
                each transition block, useful in segmentation for controlling
                the receptive field, particularly when combined with
                transition_dilation_rate.
            activation: Type of activation at the top layer. Can be one of
               'softmax' or 'sigmoid'. Note that if sigmoid is used,
                classes must be 1.

        # Returns
            A Keras model instance.
        """

    if weights not in {'cifar10', None}:
        raise ValueError('The `weights` argument should be either '
                         '`None` (random initialization) or `cifar10` '
                         '(pre-training on CIFAR-10).')

    if weights == 'cifar10' and include_top and classes != 10:
        raise ValueError('If using `weights` as CIFAR 10 with `include_top`'
                         ' as true, `classes` should be 10')

    if activation not in ['softmax', 'sigmoid']:
        raise ValueError('activation must be one of "softmax" or "sigmoid"')
    if activation == 'sigmoid' and classes != 1:
        raise ValueError('sigmoid activation can only be used when classes = 1')
    # Determine proper input shape
    # If doing segmentation we still include
    # top but _obtain_input_shape only
    # supports labeling.
    input_shape = _obtain_input_shape(input_shape,
                                      default_size=32,
                                      min_size=8,
                                      data_format=K.image_data_format(),
                                      include_top=(include_top and transition_dilation_rate is 1))

    if input_tensor is None:
        img_input = Input(shape=input_shape)
    else:
        if not K.is_keras_tensor(input_tensor):
            img_input = Input(tensor=input_tensor, shape=input_shape)
        else:
            img_input = input_tensor

    x = __create_dense_net(classes, img_input, include_top, top, depth, nb_dense_block,
                           growth_rate, nb_filter, nb_layers_per_block, bottleneck,
                           reduction, dropout_rate, weight_decay, transition_dilation_rate,
                           transition_pooling, transition_kernel_size, input_shape,
                           activation)

    # Ensure that the model takes into account
    # any potential predecessors of `input_tensor`.
    if input_tensor is not None:
        inputs = get_source_inputs(input_tensor)
    else:
        inputs = img_input
    # Create model.
    model = Model(inputs, x, name='densenet')

    # load weights
    if weights == 'cifar10':
        if (depth == 40) and (nb_dense_block == 3) and (growth_rate == 12) and (nb_filter == 16) and \
                (bottleneck is False) and (reduction == 0.0) and (dropout_rate == 0.0) and (weight_decay == 1E-4):
            # Default parameters match. Weights for this model exist:

            if K.image_data_format() == 'channels_first':
                if include_top:
                    weights_path = get_file('densenet_40_12_th_dim_ordering_th_kernels.h5',
                                            TH_WEIGHTS_PATH,
                                            cache_subdir='models')
                else:
                    weights_path = get_file('densenet_40_12_th_dim_ordering_th_kernels_no_top.h5',
                                            TH_WEIGHTS_PATH_NO_TOP,
                                            cache_subdir='models')

                model.load_weights(weights_path)

                if K.backend() == 'tensorflow':
                    warnings.warn('You are using the TensorFlow backend, yet you '
                                  'are using the Theano '
                                  'image dimension ordering convention '
                                  '(`image_dim_ordering="th"`). '
                                  'For best performance, set '
                                  '`image_dim_ordering="tf"` in '
                                  'your Keras config '
                                  'at ~/.keras/keras.json.')
                    convert_all_kernels_in_model(model)
            else:
                if include_top:
                    weights_path = get_file('densenet_40_12_tf_dim_ordering_tf_kernels.h5',
                                            TF_WEIGHTS_PATH,
                                            cache_subdir='models')
                else:
                    weights_path = get_file('densenet_40_12_tf_dim_ordering_tf_kernels_no_top.h5',
                                            TF_WEIGHTS_PATH_NO_TOP,
                                            cache_subdir='models')

                model.load_weights(weights_path)

                if K.backend() == 'theano':
                    convert_all_kernels_in_model(model)

    return model


def DenseNetFCN(input_shape, nb_dense_block=5, growth_rate=16,
                nb_layers_per_block=4, reduction=0.0, dropout_rate=0.0,
                weight_decay=1E-4, init_conv_filters=48,
                include_top=True, top='segmentation',
                weights=None, input_tensor=None, classes=1,
                activation='softmax',
                upsampling_conv=128, upsampling_type='upsampling',
                batchsize=None,
                transition_dilation_rate=1,
                transition_pooling="avg",
                transition_kernel_size=(1, 1)):
    """Instantiate the DenseNet FCN architecture.
        Note that when using TensorFlow,
        for best performance you should set
        `image_dim_ordering="tf"` in your Keras config
        at ~/.keras/keras.json.

        # Arguments
            nb_dense_block: number of dense blocks to add to end (generally = 5)
            growth_rate: number of filters to add per dense block
            nb_layers_per_block: number of layers in each dense block.
                Can be a positive integer or a list.
                If positive integer, a set number of layers per dense block.
                If list, nb_layer is used as provided. Note that list size must
                be (nb_dense_block + 1)
            reduction: reduction factor of transition blocks with
                0 <= reduction < 1.
                Note : reduction value is inverted to compute compression.
            dropout_rate: dropout rate
            weight_decay: weight decay factor
            init_conv_filters: number of layers in the initial convolution layer
            include_top: whether to include the fully-connected
                layer at the top of the network.
            weights: one of `None` (random initialization) or
                "cifar10" (pre-training on CIFAR-10)..
            input_tensor: optional Keras tensor (i.e. output of `layers.Input()`)
                to use as image input for the model.
            input_shape: optional shape tuple, only to be specified
                if `include_top` is False (otherwise the input shape
                has to be `(32, 32, 3)` (with `tf` dim ordering)
                or `(3, 32, 32)` (with `th` dim ordering).
                It should have exactly 3 inputs channels,
                and width and height should be no smaller than 8.
                E.g. `(200, 200, 3)` would be one valid value.
            classes: optional number of classes to classify images
                into, only to be specified if `include_top` is True, and
                if no `weights` argument is specified.
            activation: Type of activation at the top layer. Can be one of
                'softmax' or 'sigmoid'. Note that if sigmoid is used,
                classes must be 1.
            upsampling_conv: number of convolutional layers in upsampling via subpixel convolution
            upsampling_type: Can be one of 'upsampling', 'deconv', and
                'subpixel'. Defines type of upsampling algorithm used.
            batchsize: Fixed batch size. This is a temporary requirement for
                computation of output shape in the case of Deconvolution2D layers.
                Parameter will be removed in next iteration of Keras, which infers
                output shape of deconvolution layers automatically.
            transition_dilation_rate: An integer or tuple/list of 2 integers,
                specifying the dilation rate to in transition blocks for
                dilated convolution, increasing the receptive field of the
                algorithm. Can be a single integer to specify the same value
                for all spatial dimensions.
            transition_pooling: Data pooling to reduce resolution in transition
                blocks, one of "avg", "max", or None.
            transition_kernel_size: Adjusts the filter size of the Conv2D in
                each transition block, useful in segmentation for controlling
                the receptive field, particularly when combined with
                transition_dilation_rate.

        # Returns
            A Keras model instance.
    """

    if weights not in {None}:
        raise ValueError('The `weights` argument should be '
                         '`None` (random initialization) as no '
                         'model weights are provided.')

    upsampling_type = upsampling_type.lower()

    if upsampling_type not in ['upsampling', 'deconv', 'subpixel']:
        raise ValueError('Parameter "upsampling_type" must be one of '
                         '"upsampling", "deconv", or "subpixel".')

    if upsampling_type == 'deconv' and batchsize is None:
        raise ValueError('If "upsampling_type" is deconvoloution, then a fixed '
                         'batch size must be provided in batchsize parameter.')

    if input_shape is None:
        raise ValueError(
            'For fully convolutional models, input shape must be supplied.')

    if type(nb_layers_per_block) is not list and nb_dense_block < 1:
        raise ValueError('Number of dense layers per block must be greater than 1. Argument '
                         'value was %d.' % (nb_layers_per_block))

    if activation not in ['softmax', 'sigmoid']:
        raise ValueError('activation must be one of "softmax" or "sigmoid"')

    if activation == 'sigmoid' and classes != 1:
        raise ValueError('sigmoid activation can only be used when classes = 1')

    # Determine proper input shape
    # If doing segmentation we still include top
    # but _obtain_input_shape only supports
    # labeling, not segmentation networks.
    input_shape = _obtain_input_shape(input_shape,
                                      default_size=32,
                                      min_size=16,
                                      data_format=K.image_data_format(),
                                      include_top=False)

    if input_tensor is None:
        img_input = Input(shape=input_shape)
    else:
        if not K.is_keras_tensor(input_tensor):
            img_input = Input(tensor=input_tensor, shape=input_shape)
        else:
            img_input = input_tensor

    x = __create_fcn_dense_net(classes, img_input, include_top, nb_dense_block,
                               growth_rate, reduction, dropout_rate, weight_decay,
                               nb_layers_per_block, upsampling_conv, upsampling_type,
                               batchsize, init_conv_filters, input_shape, transition_dilation_rate,
                               transition_pooling, transition_kernel_size,
                               activation, input_shape)

    # Ensure that the model takes into account
    # any potential predecessors of `input_tensor`.
    if input_tensor is not None:
        inputs = get_source_inputs(input_tensor)
    else:
        inputs = img_input
    # Create model.
    model = Model(inputs, x, name='fcn-densenet')

    return model


def __conv_block(ip, nb_filter, bottleneck=False, dropout_rate=None, weight_decay=1E-4):
    ''' Apply BatchNorm, Relu, 3x3 Conv2D, optional bottleneck block and dropout

    Args:
        ip: Input keras tensor
        nb_filter: number of filters
        bottleneck: add bottleneck block
        dropout_rate: dropout rate
        weight_decay: weight decay factor

    Returns: keras tensor with batch_norm, relu and convolution2d added (optional bottleneck)
    '''

    concat_axis = 1 if K.image_data_format() == "channels_first" else -1

    x = BatchNormalization(axis=concat_axis, gamma_regularizer=l2(weight_decay),
                           beta_regularizer=l2(weight_decay))(ip)
    x = Activation('relu')(x)

    if bottleneck:
        # Obtained from
        # https://github.com/liuzhuang13/DenseNet/blob/master/densenet.lua
        inter_channel = nb_filter * 4

        x = Conv2D(inter_channel, (1, 1), kernel_initializer='he_uniform',
                   padding='same', use_bias=False,
                   kernel_regularizer=l2(weight_decay))(x)

        if dropout_rate:
            x = Dropout(dropout_rate)(x)

        x = BatchNormalization(mode=0, axis=concat_axis,
                               gamma_regularizer=l2(weight_decay),
                               beta_regularizer=l2(weight_decay))(x)
        x = Activation('relu')(x)

    x = Conv2D(nb_filter, (3, 3), kernel_initializer="he_uniform",
               padding="same", use_bias=False,
               kernel_regularizer=l2(weight_decay))(x)
    if dropout_rate:
        x = Dropout(dropout_rate)(x)

    return x


def __transition_block(ip, nb_filter, compression=1.0, dropout_rate=None,
                       weight_decay=1E-4, dilation_rate=1, pooling="avg",
                       kernel_size=(1, 1)):
    ''' Apply BatchNorm, Relu 1x1, Conv2D, optional compression, dropout and Maxpooling2D

    Args:
        ip: keras tensor
        nb_filter: number of filters
        compression: calculated as 1 - reduction. Reduces the number of
            feature maps in the transition block.
        dropout_rate: dropout rate
        weight_decay: weight decay factor
        dilation_rate: an integer or tuple/list of 2 integers, specifying the
          dilation rate to use for dilated, or atrous convolution.
          Can be a single integer to specify the same value for all
          spatial dimensions.
        pooling: Data pooling to reduce resolution,
            one of "avg", "max", or None.

    Returns:

        keras tensor, after applying batch_norm, relu-conv, dropout, maxpool
    '''

    concat_axis = 1 if K.image_data_format() == 'channels_first' else -1

    x = BatchNormalization(axis=concat_axis,
                           gamma_regularizer=l2(weight_decay),
                           beta_regularizer=l2(weight_decay))(ip)
    x = Activation('relu')(x)
    x = Conv2D(int(nb_filter * compression), kernel_size,
               kernel_initializer="he_uniform", padding="same", use_bias=False,
               kernel_regularizer=l2(weight_decay),
               dilation_rate=dilation_rate)(x)
    if dropout_rate:
        x = Dropout(dropout_rate)(x)

    if pooling == "avg":
        x = AveragePooling2D((2, 2), strides=(2, 2))(x)
    elif pooling == "max":
        x = MaxPooling2D((2, 2), strides=(2, 2))(x)

    return x


def __dense_block(x, nb_layers, nb_filter, growth_rate, bottleneck=False, dropout_rate=None, weight_decay=1E-4,
                  grow_nb_filters=True, return_concat_list=False):
    ''' Build a dense_block where the output of each conv_block is fed to subsequent ones

    Args:
        x: keras tensor
        nb_layers: the number of layers of conv_block to append to the model.
        nb_filter: number of filters
        growth_rate: growth rate
        bottleneck: bottleneck block
        dropout_rate: dropout rate
        weight_decay: weight decay factor
        grow_nb_filters: flag to decide to allow number of filters to grow
        return_concat_list: return the list of feature maps along with the actual output

    Returns: keras tensor with nb_layers of conv_block appended
    '''

    concat_axis = 1 if K.image_data_format() == 'channels_first' else -1

    x_list = [x]

    for i in range(nb_layers):
        x = __conv_block(x, growth_rate, bottleneck,
                         dropout_rate, weight_decay)
        x_list.append(x)

        x = merge(x_list, mode='concat', concat_axis=concat_axis)
        # x = concatenate(x_list, concat_axis)

        if grow_nb_filters:
            nb_filter += growth_rate

    if return_concat_list:
        return x, nb_filter, x_list
    else:
        return x, nb_filter


def __transition_up_block(ip, nb_filters, type='upsampling', output_shape=None, weight_decay=1E-4):
    ''' SubpixelConvolutional Upscaling (factor = 2)

    Args:
        ip: keras tensor
        nb_filters: number of layers
        type: can be 'upsampling', 'subpixel', or 'deconv'. Determines type of upsampling performed
        output_shape: required if type = 'deconv'. Output shape of tensor
        weight_decay: weight decay factor

    Returns: keras tensor, after applying upsampling operation.
    '''

    if type == 'upsampling':
        x = UpSampling2D()(ip)
    elif type == 'subpixel':
        x = Conv2D(nb_filters, (3, 3), activation="relu", padding='same', kernel_regularizer=l2(weight_decay),
                   use_bias=False, kernel_initializer='he_uniform')(ip)
        x = SubPixelUpscaling(scale_factor=2)(x)
        x = Conv2D(nb_filters, (3, 3), activation="relu", padding='same', kernel_regularizer=l2(weight_decay),
                   use_bias=False, kernel_initializer='he_uniform')(x)
    else:
        x = Conv2DTranspose(nb_filters, (3, 3), output_shape, activation='relu', padding='same',
                            subsample=(2, 2), kernel_initializer='he_uniform')(ip)

    return x


def __create_dense_net(nb_classes, img_input, include_top=True,
                       top='classification', depth=40,
                       nb_dense_block=3, growth_rate=12, nb_filter=-1,
                       nb_layers_per_block=-1, bottleneck=False, reduction=0.0,
                       dropout_rate=None, weight_decay=1E-4,
                       transition_dilation_rate=1, transition_pooling="avg",
                       transition_kernel_size=(1, 1), input_shape=None,
                       activation='softmax'):
    ''' Build the DenseNet model

    Args:
        nb_classes: number of classes
        img_input: tuple of shape (channels, rows, columns) or
            (rows, columns, channels)
        include_top: flag to include the final Dense layer
        depth: number or layers
        nb_dense_block: number of dense blocks to add to end (generally = 3)
        growth_rate: number of filters to add per dense block
        nb_filter: initial number of filters. Default -1 indicates
            initial number of filters is 2 * growth_rate.
        nb_layers_per_block: number of layers in each dense block.
            Can be a -1, positive integer or a list.
            If -1, calculates nb_layer_per_block from the depth of the network.
            If positive integer, a set number of layers per dense block.
            If list, nb_layer is used as provided. Note that list size must
            be (nb_dense_block + 1)
        bottleneck: add bottleneck blocks
        reduction: reduction factor of transition blocks.
            Note : reduction value is inverted to compute compression
        dropout_rate: dropout rate
        weight_decay: weight decay
        transition_dilation_rate: An integer or tuple/list of 2 integers,
            specifying the dilation rate to in transition blocks for
            dilated convolution, increasing the receptive field of the
            algorithm. Can be a single integer to specify the same value
            for all spatial dimensions.
        transition_pooling: Data pooling to reduce resolution in transition
            blocks, one of "avg", "max", or None.
        transition_kernel_size: Adjusts the filter size of the Conv2D in
            each transition block, useful in segmentation for controlling
            the receptive field, particularly when combined with
            transition_dilation_rate.
        input_shape: Only used for shape inference in fully convolutional networks.
        activation: Type of activation at the top layer. Can be one of
            'softmax' or 'sigmoid'. Note that if sigmoid is used,
            classes must be 1.

    Returns: keras tensor with nb_layers of conv_block appended
    '''

    concat_axis = 1 if K.image_data_format() == 'channels_first' else -1

    if depth is not None:
        assert (depth - 4) % 3 == 0, "Depth must be nb_dense_block * N + 4"
    else:
        assert nb_layers_per_block is not -1, "Depth cannot be None when nb_layers_per_block is -1. Specify either parameter."
    if reduction != 0.0:
        assert reduction <= 1.0 and reduction > 0.0, "reduction value must lie between 0.0 and 1.0"

    # layers in each dense block
    if type(nb_layers_per_block) is list or type(nb_layers_per_block) is tuple:
        nb_layers = list(nb_layers_per_block)  # Convert tuple to list

        assert len(nb_layers) == (nb_dense_block + 1), "If list, nb_layer is used as provided. " \
                                                       "Note that list size must be (nb_dense_block + 1)"
        final_nb_layer = nb_layers[-1]
        nb_layers = nb_layers[:-1]
    else:
        if nb_layers_per_block == -1:
            count = int((depth - 4) / 3)
            nb_layers = [count for _ in range(nb_dense_block)]
            final_nb_layer = count
        else:
            final_nb_layer = nb_layers_per_block
            nb_layers = [nb_layers_per_block] * nb_dense_block

    if bottleneck:
        nb_layers = [int(layer // 2) for layer in nb_layers]

    # compute initial nb_filter if -1, else accept users initial nb_filter
    if nb_filter <= 0:
        nb_filter = 2 * growth_rate

    # compute compression factor
    compression = 1.0 - reduction

    # Initial convolution
    x = Conv2D(nb_filter, (3, 3), kernel_initializer="he_uniform",
               padding="same", name="initial_conv2D", use_bias=False,
               kernel_regularizer=l2(weight_decay))(img_input)

    # Add dense blocks
    for block_idx in range(nb_dense_block - 1):
        x, nb_filter = __dense_block(x, nb_layers[block_idx], nb_filter,
                                     growth_rate, bottleneck=bottleneck,
                                     dropout_rate=dropout_rate,
                                     weight_decay=weight_decay)
        # add transition_block
        x = __transition_block(x, nb_filter, compression=compression,
                               dropout_rate=dropout_rate,
                               weight_decay=weight_decay,
                               dilation_rate=transition_dilation_rate,
                               pooling=transition_pooling,
                               kernel_size=transition_kernel_size)
        nb_filter = int(nb_filter * compression)

    # The last dense_block does not have a transition_block
    x, nb_filter = __dense_block(x, final_nb_layer, nb_filter, growth_rate, bottleneck=bottleneck,
                                 dropout_rate=dropout_rate, weight_decay=weight_decay)

    x = BatchNormalization(axis=concat_axis, gamma_regularizer=l2(weight_decay),
                           beta_regularizer=l2(weight_decay))(x)
    x = Activation('relu')(x)

    if include_top and top is 'classification':
        x = GlobalAveragePooling2D()(x)
        x = Dense(nb_classes, activation=activation, kernel_regularizer=l2(
            weight_decay), bias_regularizer=l2(weight_decay))(x)
    elif include_top and top is 'segmentation':
        x = Conv2D(nb_classes, (1, 1), activation='linear', padding='same', kernel_regularizer=l2(weight_decay),
                   use_bias=False)(x)

        if K.image_data_format() == 'channels_first':
            channel, row, col = input_shape
        else:
            row, col, channel = input_shape

        x = Reshape((row * col, nb_classes))(x)
        x = Activation(activation)(x)
        x = Reshape((row, col, nb_classes))(x)

    return x


def __create_fcn_dense_net(nb_classes, img_input, include_top, nb_dense_block=5, growth_rate=12,
                           reduction=0.0, dropout_rate=None, weight_decay=1E-4,
                           nb_layers_per_block=4, nb_upsampling_conv=128, upsampling_type='upsampling',
                           batchsize=None, init_conv_filters=48,
                           transition_dilation_rate=1,
                           transition_pooling='avg',
                           transition_kernel_size=(1, 1),
                           activation='softmax',
                           input_shape=None):
    ''' Build the DenseNet model

    Args:
        nb_classes: number of classes
        img_input: tuple of shape (channels, rows, columns) or (rows, columns, channels)
        include_top: flag to include the final Dense layer
        nb_dense_block: number of dense blocks to add to end (generally = 3)
        growth_rate: number of filters to add per dense block
        reduction: reduction factor of transition blocks. Note : reduction value is inverted to compute compression
        dropout_rate: dropout rate
        weight_decay: weight decay
        nb_layers_per_block: number of layers in each dense block.
            Can be a positive integer or a list.
            If positive integer, a set number of layers per dense block.
            If list, nb_layer is used as provided. Note that list size must
            be (nb_dense_block + 1)
        nb_upsampling_conv: number of convolutional layers in upsampling via subpixel convolution
        upsampling_type: Can be one of 'upsampling', 'deconv', and
            'subpixel'. Defines type of upsampling algorithm used.
        batchsize: Fixed batch size. This is a temporary requirement for
            computation of output shape in the case of Deconvolution2D layers.
            Parameter will be removed in next iteration of Keras, which infers
            output shape of deconvolution layers automatically.
        input_shape: Only used for shape inference in fully convolutional networks.
        transition_dilation_rate: An integer or tuple/list of 2 integers,
            specifying the dilation rate to in transition blocks for
            dilated convolution, increasing the receptive field of the
            algorithm. Can be a single integer to specify the same value
            for all spatial dimensions.
        transition_pooling: Data pooling to reduce resolution in transition
            blocks, one of "avg", "max", or None.
        transition_kernel_size: Adjusts the filter size of the Conv2D in
            each transition block, useful in segmentation for controlling
            the receptive field, particularly when combined with
            transition_dilation_rate.

    Returns: keras tensor with nb_layers of conv_block appended
    '''

    concat_axis = 1 if K.image_data_format() == "channels_first" else -1

    if concat_axis == 1:  # th dim ordering
        _, rows, cols = input_shape
    else:
        rows, cols, _ = input_shape

    if reduction != 0.0:
        assert reduction <= 1.0 and reduction > 0.0, "reduction value must lie between 0.0 and 1.0"

    # check if upsampling_conv has minimum number of filters
    # minimum is set to 12, as at least 3 color channels are needed for
    # correct upsampling
    assert nb_upsampling_conv >= 12 and nb_upsampling_conv % 4 == 0, "Parameter `upsampling_conv` number of channels must " \
                                                                    "be a positive number divisible by 4 and greater " \
                                                                    "than 12"

    # layers in each dense block
    if type(nb_layers_per_block) is list or type(nb_layers_per_block) is tuple:
        nb_layers = list(nb_layers_per_block)  # Convert tuple to list

        assert len(nb_layers) == (nb_dense_block + 1), "If list, nb_layer is used as provided. " \
                                                       "Note that list size must be (nb_dense_block + 1)"

        bottleneck_nb_layers = nb_layers[-1]
        rev_layers = nb_layers[::-1]
        nb_layers.extend(rev_layers[1:])
    else:
        bottleneck_nb_layers = nb_layers_per_block
        nb_layers = [nb_layers_per_block] * (2 * nb_dense_block + 1)

    # compute compression factor
    compression = 1.0 - reduction

    # Initial convolution
    x = Conv2D(init_conv_filters, (3, 3), kernel_initializer="he_uniform", padding="same", name="initial_conv2D", use_bias=False,
               kernel_regularizer=l2(weight_decay))(img_input)

    nb_filter = init_conv_filters

    skip_list = []

    # Add dense blocks and transition down block
    for block_idx in range(nb_dense_block):
        x, nb_filter = __dense_block(x, nb_layers[block_idx], nb_filter, growth_rate,
                                     dropout_rate=dropout_rate, weight_decay=weight_decay)

        # Skip connection
        skip_list.append(x)

        # add transition_block
        x = __transition_block(x, nb_filter, compression=compression, dropout_rate=dropout_rate,
                               weight_decay=weight_decay)

        # this is calculated inside transition_down_block
        nb_filter = int(nb_filter * compression)

    # The last dense_block does not have a transition_down_block
    # return the concatenated feature maps without the concatenation of the
    # input
    _, nb_filter, concat_list = __dense_block(x, bottleneck_nb_layers, nb_filter, growth_rate,
                                              dropout_rate=dropout_rate, weight_decay=weight_decay,
                                              return_concat_list=True)

    skip_list = skip_list[::-1]  # reverse the skip list

    if K.image_data_format() == 'channels_first':
        out_shape = [batchsize, nb_filter, rows // 16, cols // 16]
    else:
        out_shape = [batchsize, rows // 16, cols // 16, nb_filter]

    # Add dense blocks and transition up block
    for block_idx in range(nb_dense_block):
        n_filters_keep = growth_rate * nb_layers[nb_dense_block + block_idx]

        if K.image_data_format() == 'channels_first':
            out_shape[1] = n_filters_keep
        else:
            out_shape[3] = n_filters_keep

        # upsampling block must upsample only the
        # feature maps (concat_list[1:]),
        # not the concatenation of the input with the
        # feature maps (concat_list[0]).
        l = merge(concat_list[1:], mode='concat', concat_axis=concat_axis)
        # l = concatenate(concat_list[1:], axis=concat_axis)

        t = __transition_up_block(l, nb_filters=n_filters_keep,
                                  type=upsampling_type,
                                  output_shape=out_shape)

        # concatenate the skip connection with the transition block
        x = merge([t, skip_list[block_idx]],
                  mode='concat', concat_axis=concat_axis)
        # x = concatenate([t, skip_list[block_idx]], axis=concat_axis)

        if K.image_data_format() == 'channels_first':
            out_shape[2] *= 2
            out_shape[3] *= 2
        else:
            out_shape[1] *= 2
            out_shape[2] *= 2

        # Dont allow the feature map size to grow in upsampling dense blocks
        _, nb_filter, concat_list = __dense_block(x, nb_layers[nb_dense_block + block_idx + 1], nb_filter=growth_rate,
                                                  growth_rate=growth_rate, dropout_rate=dropout_rate,
                                                  weight_decay=weight_decay,
                                                  return_concat_list=True, grow_nb_filters=False)

    if include_top and top is 'classification':
        x = Conv2D(nb_classes, (1, 1), activation='linear', padding='same', kernel_regularizer=l2(weight_decay),
                   use_bias=False)(x)

        if K.image_data_format() == 'channels_first':
            channel, row, col = input_shape
        else:
            row, col, channel = input_shape

        x = Reshape((row * col, nb_classes))(x)
        x = Activation(activation)(x)
        x = Reshape((row, col, nb_classes))(x)

    return x
