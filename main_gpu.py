# -*- coding: utf-8 -*-
"""
Created on Wed Jul 24 16:23:28 2019

@author: gcl15
"""
# imports
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import TensorDataset, DataLoader, Dataset
import torchvision.transforms as transforms
import numpy as np
from sklearn.model_selection import StratifiedShuffleSplit

import matplotlib.pyplot as plt
import h5py
import random


torch.backends.cudnn.benchmark = True
torch.backends.cudnn.enabled = True

h5py.run_tests()


## lukas' cuda stuff

device = 'cpu'
if torch.cuda.device_count() > 0 and torch.cuda.is_available():
    print("Cuda installed! Running on GPU!")
    device = 'cuda'
else:
    print("No GPU available!")
    
    
def set_seed(seed):
    """
    Use this to set ALL the random seeds to a fixed value and take out any randomness from cuda kernels
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    torch.backends.cudnn.benchmark = True  ##uses the inbuilt cudnn auto-tuner to find the fastest convolution algorithms. -
    torch.backends.cudnn.enabled   = True

    return True
  
set_seed(42)

# now for lstm unit 
class LSTMunit(nn.Module):
    def __init__(self, input_channel_no, hidden_channels_no, kernel_size, stride = 1):
        super(LSTMunit, self).__init__()
        """base unit for an overall convLSTM structure. convLSTM exists in keras but
        not pytorch. LSTMunit repersents one cell in an overall convLSTM encoder decoder format
        the structure of convLSTMs lend themselves well to compartmentalising the LSTM
        cells. 
    
        Each cell takes an input the data at the current timestep Xt, and a hidden
        representation from the previous timestep Ht-1
    
        Each cell outputs Ht
        """
    
    
        self.input_channels = input_channel_no
    
        self.output_channels = hidden_channels_no
    
        self.kernel_size = kernel_size
    
        self.padding = (int((self.kernel_size - 1) / 2 ), int((self.kernel_size - 1) / 2 ))#to ensure output image same dims as input
        # as in conv nowcasting - see references 
        self.stride = stride # for same reasons as above
        
        # need convolutions, cells, tanh, sigmoid?
        # need input size for the lstm - on size of layers.
        # cannot do this because of the modules not being registered when stored in a list
        # can if we convert it to a parameter dict
    
        # list of names of filter to put in dictionary.
        # some of these are not convolutions
        """TODO: CHANGE THIS LAYOUT OF CONVOLUTIONAL LAYERS. """
        
        
        
        self.filter_name_list = ['Wxi', 'Wxf', 'Wxc', 'Wxo','Whi', 'Whf', 'Whc', 'Who']
        
        """ TODO : DEAL WITH BIAS HERE. """ 
        """ TODO: CAN INCLUDE BIAS IN ONE OF THE CONVOLUTIONS BUT NOT ALL OF THEM - OR COULD INCLUDE IN ALL? """

        # list of concolution instances for each lstm cell step
       #  nn.Conv2d(1, 48, kernel_size=3, stride=1, padding=0),
        self.conv_list = [nn.Conv2d(self.input_channels, self.output_channels, kernel_size =  self.kernel_size, stride = self.stride, padding = self.padding, bias = False).cuda() for i in range(4)]
        self.conv_list = self.conv_list + [(nn.Conv2d(self.output_channels, self.output_channels, kernel_size =  self.kernel_size, stride = self.stride, padding = self.padding, bias = True).cuda()).double() for i in range(4)]
#         self.conv_list = nn.ModuleList(self.conv_list)
        # stores nicely in dictionary for compact readability.
        # most ML code is uncommented and utterly unreadable. Here we try to avoid this
        self.conv_dict = nn.ModuleDict(zip(self.filter_name_list, self.conv_list))
    
        # may be able to combine all the filters and combine all the things to be convolved - as long as there is no cross layer convolution
        # technically the filter will be the same? - check this later.
    
        # set up W_co, W_cf, W_co as variables.
        """ TODO: decide whether this should be put into function. """
        
        
        """TODO: put correct dimensions of tensor in shape"""
        
        # of dimensions seq length, hidden layers, height, width
        """TODO: DEFINE THESE SYMBOLS. """
        """TODO: PUT THIS IN CONSTRUCTOR."""
        shape = [1, self.output_channels, 64, 64]
        
        self.Wco = nn.Parameter((torch.zeros(shape).double()).cuda(), requires_grad = True)
        self.Wcf = nn.Parameter((torch.zeros(shape).double()).cuda(), requires_grad = True)
        self.Wci = nn.Parameter((torch.zeros(shape).double()).cuda(), requires_grad = True)
#         self.Wco.name = "test"
#         self.Wco = torch.zeros(shape, requires_grad = True).double()
#         self.Wcf = torch.zeros(shape, requires_grad = True).double()
#         self.Wci = torch.zeros(shape, requires_grad = True).double()

        # activation functions.
        self.tanh = torch.tanh
        self.sig  = torch.sigmoid

#     (1, 6, kernel_size=5, padding=2, stride=1).double()
    def forward(self, x, h, c):
        """ put the various nets in here - instanciate the other convolutions."""
        """TODO: SORT BIAS OUT HERE"""
        """TODO: PUT THIS IN SELECTOR FUNCTION? SO ONLY PUT IN WXI ECT TO MAKE EASIER TO DEBUG?"""
#         print("size of x is:")
#         print(x.shape)
        # ERROR IS IN LINE 20
        #print(self.conv_dict['Wxi'](x).shape)
#         print("X:")
#         print(x.is_cuda)
#         print("H:")
#         print(h.is_cuda)
#         print("C")
#         print(c.is_cuda)
        
        i_t = self.sig(self.conv_dict['Wxi'](x) + self.conv_dict['Whi'](h) + self.Wci * c)
        f_t = self.sig(self.conv_dict['Wxf'](x) + self.conv_dict['Whf'](h) + self.Wcf * c)
        c_t = f_t * c + i_t * self.tanh(self.conv_dict['Wxc'](x) + self.conv_dict['Whc'](h))
        o_t = self.sig(self.conv_dict['Wxo'](x) + self.conv_dict['Who'](h) + self.Wco * c_t)
        h_t = o_t * self.tanh(c_t)
        
        return h_t, c_t
    
    def copy_in(self):
        """dummy function to copy in the internals of the output in the various architectures i.e encoder decoder format"""


class LSTMmain(nn.Module):
    
    
    """ collection of units to form encoder/ decoder branches - decide which are which
    need funcitonality to copy in and copy out outputs.
    
    
    layer output is array of booleans selectively outputing for each layer i.e 
    for three layer can have output on second and third but not first with 
    layer_output = [0,1,1]"""
    
    """TODO: DECIDE ON OUTPUT OF HIDDEN CHANNEL LIST """
    def __init__(self, shape, input_channel_no, hidden_channel_no, kernel_size, layer_output, test_input, copy_bool = False, debug = False, save_outputs = True, decoder = False, second_debug = False):
        super(LSTMmain, self).__init__()
        
        """TODO: USE THIS AS BASIS FOR ENCODER DECODER."""
        """TODO: SPECIFY SHAPE OF INPUT VECTOR"""
        
        """TODO: FIGURE OUT HOW TO IMPLEMENT ENCODER DECODER ARCHITECUTRE"""
        self.copy_bool = copy_bool
        
        self.test_input = test_input
        
        self.debug = debug
        self.second_debug = second_debug
        self.save_all_outputs = save_outputs
        
        self.shape = shape
        
        """specify dimensions of shape - as in channel length ect. figure out once put it in a dataloader"""
        
        self.layers = len(test_input) #number of layers in the encoder. 
        
        self.seq_length = shape[1]
        
        self.enc_len = len(shape)
        
        self.input_chans = input_channel_no
        
        self.hidden_chans = hidden_channel_no
        
        self.kernel_size = kernel_size
        
        self.layer_output = layer_output
        
        # initialise the different conv cells. 
#         self.unit_list = [LSTMunit(input_channel_no, hidden_channel_no, kernel_size) for i in range(self.enc_len)]
        self.dummy_list = [input_channel_no] + list(self.test_input) # allows test input to be an array
        if self.debug:
            print("dummy_list:")
            print(self.dummy_list)
            
#         self.unit_list = nn.ModuleList([(LSTMunit(self.dummy_list[i], self.dummy_list[i+1], kernel_size).double()).cuda() for i in range(len(self.test_input))])
        self.unit_list = nn.ModuleList([(LSTMunit(self.dummy_list[i], self.dummy_list[i+1], kernel_size).double()).cuda() for i in range(len(self.test_input))])
        
        if self.debug:
            print("number of units:")
            print(len(self.unit_list))
#             print("number of ")

#         self.unit_list = nn.ModuleList(self.unit_list)
    
    
    def forward(self, x, copy_in = False, copy_out = [False, False, False]):
#     def forward(self, x):
#         copy_in = False
#         copy_out = [False, False, False]

        
#         print("IS X CUDA?")
#         print(x.is_cuda)
        """loop over layers, then over hidden states
        
        copy_in is either False or is [[h,c],[h,c]] ect.
        
        THIS IN NOW CHANGED TO COPY IN 
        
        """
        
        internal_outputs = []
        """TODO: HOW MANY OUTPUTS TO SAVE"""
        """ S """
        
        """ TODO: PUT INITIAL ZERO THROUGH THE SYSTEM TO DEFINE H AND C"""
        
        layer_output = [] # empty list to save each h and c for each step. 
        """TODO: DECIDE WHETHER THE ABOVE SHOULD BE ARRAY OR NOT"""
        
        # x is 5th dimensional tensor.
        # x is of size batch, sequence, layers, height, width
        
        """TODO: INITIALISE THESE WITH VECTORS."""
        # these need to be of dimensions (batchsizze, hidden_dim, heigh, width)
        
        size = x.shape
        
        # need to re arrange the outputs. 
        
        
        """TODO: SORT OUT H SIZING. """
        
        batch_size = size[0]
        # change this. h should be of dimensions hidden size, hidden size.
        h_shape = list(x.shape[:1] + x.shape[2:]) # seq is second, we miss it with fancy indexing
        h_shape[1] = self.hidden_chans
        if self.debug:
            print("h_shape:")
            print(h_shape)
        
        # size should be (seq, batch_size, layers, height, weight)
        
        
        empty_start_vectors = []
        
        
        #### new method of copying vectors. copy_bool, assigned during object 
        # construction now deals iwth copying in values.
        # copy in is still used to supply the tensor values. 
    
        k = 0 # to count through our input state list.
        for i in range(self.layers):
            if self.copy_bool[i]: # if copy bool is true for this layer
                # check purpose of h_shape in below code.
                empty_start_vectors.append(copy_in[k])
                # copies in state for that layer
                """TODO: CHECK IF THIS NEEDS TO BE DETATCHED OR NOT"""
                k += 1 # iterate through input list.
            
            else: # i.e if false
                assert self.copy_bool[i] == False, "copy_bool arent bools"
                
                h_shape = list(x.shape[:1] + x.shape[2:]) # seq is second, we miss it with fancy indexing
                h_shape[1] = self.dummy_list[i+1] # check indexing. 
                empty_start_vectors.append([(torch.zeros(h_shape).double()).cuda(), (torch.zeros(h_shape).double()).cuda()])
                
        del k # clear up k so no spare variables flying about.
        
        
        
        
#         for i in range(self.layers):
#             """CHANGED: NOW HAS COPY IN COPY OUT BASED ON [[0,0][H,C]] FORMAT"""
#             if copy_in == False: # i.e if no copying in occurs then proceed as normal
#                 h_shape = list(x.shape[:1] + x.shape[2:]) # seq is second, we miss it with fancy indexing
#                 h_shape[1] = self.dummy_list[i+1] # check indexing. 
# #                 empty_start_vectors.append([(torch.zeros(h_shape).double()).cuda(), (torch.zeros(h_shape).double()).cuda()])
#                 empty_start_vectors.append([(torch.zeros(h_shape).double()).cuda(), (torch.zeros(h_shape).double()).cuda()])
# #             elif copy_in[i] == [0,0]:
#             elif isinstance(copy_in[i], list):

#                 assert (len(copy_in) == self.layers), "Length disparity between layers, copy in format"

#                 # if no copying in in alternate format
#                 h_shape = list(x.shape[:1] + x.shape[2:]) # seq is second, we miss it with fancy indexing
#                 h_shape[1] = self.dummy_list[i+1] # check indexing. 
#                 empty_start_vectors.append([(torch.zeros(h_shape).double()).cuda(), (torch.zeros(h_shape).double()).cuda()])
                
#             else: # copy in the provided vectors
#                 assert (len(copy_in) == self.layers), "Length disparity between layers, copy in format"

#                 """TODO: DECIDE WHETHER TO CHANGE THIS TO AN ASSERT BASED OFF TYPE OF TENSOR."""
#                 empty_start_vectors.append(copy_in[i])
                
            
        
        
        
#         empty_start_vectors = [[torch.zeros(h_shape), torch.zeros(h_shape)] for i in range(self.layers)]
        
        
        
        if self.debug:
            for i in empty_start_vectors:
                print(i[0].shape)
            print(" \n \n \n")
        
#         for i in range(self.layers):
#             empty_start_vectors.append([torch.tensor()])
        
        total_outputs = []
        
        
        for i in range(self.layers):
            
            
            layer_output = []
            if self.debug:
                print("layer iteration:")
                print(i)
            # for each in layer

            """AS WE PUT IN ZEROS EACH TIME THIS MAKES OUR LSTM STATELESS"""
            # initialise with zero or noisy vectors 
            # at start of each layer put noisy vector in 
            # look at tricks paper to find more effective ideas of how to put this in
            # do we have to initialise with 0 tensors after we go to the second layer
            # or does the h carry over???
            """TODO: REVIEW THIS CHANGE"""
            
            # copy in for each layer. 
            # this is used for encoder decoder architectures.
            # default is to put in empty vectors. 
            
            """TODO: REVIEW THIS SECTION"""
            """CHANGED: TO ALWAYS CHOOSE H AND C"""
#             if copy_in == False:
#                 h, c = empty_start_vectors[i]
#             else: h, c = copy_in[i]

            h, c = empty_start_vectors[i] 
                
            if self.debug:
                print("new h shape")
                print(h.shape)
                
            """TODO: DO WE HAVE TO PUT BLANK VECTORS IN AT EACH TIMESTEP?"""
            
            # need to initialise zero states for c and h. 
            for j in range(self.seq_length):
                if self.debug:
                    print("inner loop iteration:")
                    print(j)
                if self.debug:
                    print("x dtype is:" , x.dtype)
                # for each step in the sequence
                # put x through 
                # i.e put through each x value at a given time.
                
                """TODO: PUT H IN FROM PREVIOUS LAYER, BUT C SHOULD BE ZEROS AT START"""
                
                if self.debug:
                    print("inner loop size:")
                    print(x[:,j].shape)
                    print("h size:")
                    print(h.shape)
                    
                h, c = self.unit_list[i](x[:,j], h, c)
                
                # this is record for each output in given layer.
                # this depends whether copying out it enabld 
#                 i
                layer_output.append([h, c])
                
            """TODO: IMPLEMENT THIS"""
#             if self.save_all_outputs[i]:
#                 total_outputs.append(layer_outputs[:,0]) # saves h from each of the layer outputs
                
            # output 
            """OUTSIDE OF SEQ LOOP"""
            """TODO: CHANGE TO NEW OUTPUT METHOD."""
            if copy_out[i] == True:
                # if we want to copy out the contents of this layer:
                internal_outputs.append(layer_output[-1])
                # saves last state and memory which can be subsequently unrolled.
                # when used in an encoder decoder format.
            """removed else statement"""
#             else:
#                 internal_outputs.append([0,0])
                # saves null variable so we can check whats being sent out.
            
            
            h_output = [i[0] for i in layer_output] #layer_output[:,0] # take h from each timestep.
            if self.debug:
                print("h_output is of size:")
                print(h_output[0].shape)
                
                      
            """TODO: REVIEW IF 1 IS THE CORRECT AXIS TO CONCATENATE THE VECTORS ALONG"""
            # we now use h as the predictor input to the other layers.
            """TODO: STACK TENSORS ALONG NEW AXIS. """
            
            
            x = torch.stack(h_output,0)
            x = torch.transpose(x, 0, 1)
            if self.second_debug:
                print("x shape in LSTM main:" , x.shape)
            if self.debug:
                print("x reshaped dimensions:")
                print(x.shape)
        
#         x = torch.zeros(x.shape)
#         x.requires_grad = True
        return x , internal_outputs # return new h in tensor form. do we need to cudify this stuff

    def initialise(self):
        """put through zeros to start everything"""
        
class LSTMencdec_onestep(nn.Module):
    """structure is overall architecture of """
    def __init__(self, structure, input_channels, kernel_size = 5, debug = True):
        super(LSTMencdec_onestep, self).__init__()
#         assert isinstance(structure, np.array), "structure should be a 2d numpy array"
        assert len(structure.shape) == 2, "structure should be a 2d numpy array with two rows"
        self.debug = debug
        
        """TODO: MAKE KERNEL SIZE A LIST SO CAN SPECIFY AT EACH JUNCTURE."""
        shape = [1,10,1,64,64]
        
        self.structure = structure
        """STRUCTURE IS AN ARRAY - CANNOT USE [] + [] LIST CONCATENATION - WAS ADDING ONE ONTO THE ARRAY THING."""
        self.input_channels = input_channels
        self.kernel_size = kernel_size
        
        """TODO: ASSERT THAT DATATYPE IS INT."""
        
        self.enc_shape, self.dec_shape, self.enc_copy_out, self.dec_copy_in = self.input_test()
        
        if self.debug:
            print("enc_shape, dec_shape, enc_copy_out, dec_copy_in:")
            print(self.enc_shape)
            print(self.dec_shape)
            print(self.enc_copy_out)
            print(self.dec_copy_in)
            
        
        
#         self.sig = nn.Sigmoid()
        
         # why does this have +1 at third input and decoder hasnt?????? 
        
        self.encoder = LSTMmain(shape, self.input_channels, len(self.enc_shape)+1, self.kernel_size, layer_output = self.enc_copy_out, test_input = self.enc_shape, copy_bool = [False for k in range(len(self.enc_shape))]  ).cuda()
        # now one step in sequence
        shape = [1,1,1,64,64]

        self.decoder = LSTMmain(shape, self.enc_shape[-1], len(self.dec_shape), self.kernel_size, layer_output = 1, test_input = self.dec_shape, copy_bool = self.dec_copy_in,  second_debug = False).cuda()
        
        
        
        # initialise encoder and decoder network
    
    def input_test(self):
        """check input structure to make sure there is overlap between encoder 
        and decoder.
        """
        copy_grid = []
        # finds dimensions of the encoder
        enc_layer = self.structure[0]
        enc_shape = enc_layer[enc_layer!=0]
        dec_layer = self.structure[1]
        dec_shape = dec_layer[dec_layer!=0]
#         
        
        
        
        
        
        #set up boolean grid of where the overlaps are.
        for i in range(len(enc_layer)):
            if self.debug:
                print(enc_layer[i], dec_layer[i])
            if (enc_layer[i] != 0) and (dec_layer[i] != 0):
                copy_grid.append(True)
            else:
                copy_grid.append(False)
                
                
        enc_overlap = copy_grid[:len(enc_layer)-1]
        
        num_dec_zeros = len(dec_layer[dec_layer==0]) # will this break if no zeros?
        
        dec_overlap = copy_grid[num_dec_zeros:]
        
        return enc_shape, dec_shape, enc_overlap, dec_overlap
        
#         dec_overlap = copy_grid[]                
        
                
                
#         [[1,2,3,0],
#          [0,2,3,1]]
    def forward(self, x):
        
        x, out_states = self.encoder(x, copy_in = False, copy_out = self.enc_copy_out)
        
#         print("length of out_states:", len(out_states))
#         print("contents out outstates are as follows:")
#         for i in out_states:
#             print("----------------------------------")
#             print("first object type:", type(i[0]))
# #             print("length of object:", len(i[0]))
            
        
        
        
        dummy_input = torch.zeros(x.shape)
        # technically a conditional loader - put x in there 
        # puts in the last one as input - should make shorter. 
        # presume coming out in the correct order - next try reversing to see if that helps 
        x = x[:,-1:,:,:,:]
#         print("x shape encoder:", x.shape)
#         print(x.shape)
        
        
        res, _ = self.decoder(x, copy_in = out_states, copy_out = [False, False, False])
        print("FINISHING ONE PASS")
#         res = self.sig(res)
        return res

# now datasets and dataloades
        
    
    
class SequenceDataset(Dataset):
    """simple data set wrapper 
    for the moving mnist dataset
    
    we use this as need to insert channel dimension in the data"""
    def __init__(self, predictor, ground_truth, transform = None):
        
        self.input_sequence = predictor
        
        self.output_sequence = ground_truth
        
        assert len(self.input_sequence.shape) == 5, "internal data should be : batch_size, sequence_length, channels, height, width"
        
        
#         print(self.input_sequence.shape)
        
       
    def __len__(self):
        return len(self.input_sequence)
    
    def __getitem__(self, i):
        """returns tuple of predictor and result sequence
        
        This should later be specified to return a valid number of steps in the future
        
        i.e can specify whether want input of 10 and to predict 5 ect."""
                

        
        return self.input_sequence[i], self.output_sequence[i]
    

class HDF5Dataset(Dataset):
    """dataset wrapper for hdf5 dataset to allow for lazy loading of data. This 
    allows ram to be conserved. 
    
    As the hdf5 dataset is not partitioned into test and validation, the dataset 
    takes a shuffled list of indices to allow specification of training and 
    validation sets.
    
    MAKE SURE TO CALL DEL ON GENERATED OBJECTS OTHERWISE WE WILL CLOG UP RAM
    
    """
    
    def __init__(self, path, index_map, transform = None):
        
#        %cd /content/drive/My \Drive/masters_project/data 
        # changes directory to the one where needed.
        
        self.path = path
        
        self.index_map = index_map # maps to the index in the validation split
        # due to hdf5 lazy loading index map must be in ascending order.
        # this may be an issue as we should shuffle our dataset.
        # this will be raised as an issue as we consider a work around.
        # we should keep index map shuffled, and take the selection from the 
        # shuffled map and select in ascending order. 
        
        
        self.file = h5py.File(path, 'r')
        
        
        
        
        
        
    def __len__(self):
        return len(self.index_map)
    
    def __getitem__(self,i):
        
        i = self.index_map[i] # index maps from validation set to select new orders
#         print(i)
        if isinstance(i, list): # if i is a list. 
            i.sort() # sorts into ascending order as specified above
            
        """TODO: CHECK IF THIS RETURNS DOUBLE"""
        
        predictor = torch.tensor(self.file["predictor"][i])
        
        truth = torch.tensor(self.file["truth"][i])
        
        return predictor, truth


def initialise_dataset_HDF5(valid_frac = 0.1, dataset_length = 9000):
    """
    Returns datasets for training and validation. 
    
    Loads in datasets segmenting for validation fractions.
   
    
    
    """
    
    if valid_frac != 0:
        
        dummy = np.array(range(dataset_length)) # clean this up - not really needed
        
        train_index, valid_index = validation_split(dummy, n_splits = 1, valid_fraction = 0.1, random_state = 0)
        
        train_dataset = HDF5Dataset("train_set.hdf5", index_map = train_index)
        
        valid_dataset = HDF5Dataset("test_set.hdf5", index_map = valid_index)
        
        return train_dataset, valid_dataset
        
    else:
        print("not a valid fraction for validation") # turn this into an assert.
        
        
        
def validation_split(data, n_splits = 1, valid_fraction = 0.1, random_state = 0):
    """
    Function to produce a validation set from test set.
    THIS SHUFFLES THE SAMPLES. __NOT__ THE SEQUENCES.
    """
    dummy_array = np.zeros(len(data))
    split = StratifiedShuffleSplit(n_splits, test_size = valid_fraction, random_state = 0)
    generator = split.split(torch.tensor(dummy_array), torch.tensor(dummy_array))
    return [(a,b) for a, b in generator][0]


def unsqueeze_data(data):
    """
    Takes in moving MNIST object - must then account for 
    """
    
    # split moving mnist data into predictor and ground truth.
    predictor = data[:][0].unsqueeze(2)
    predictor = predictor.double()
        
    truth = data[:][1].unsqueeze(2)# this should be the moving mnist sent in
    truth = truth.double()
    
    return predictor, truth
    # the data should now be unsqueezed.


def initialise_dataset(data):
    # unsqueeze data, adding a channel dimension for later convolution. 
    # this also gets rid of the annoying tuple format
    predictor, truth = unsqueeze_data(data)
    
    train_index, valid_index = validation_split(data)
    
    train_predictor = predictor[train_index]
    valid_predictor = predictor[valid_index]
    
    train_truth = truth[train_index]
    valid_truth = truth[valid_index]
    
    train_dataset = SequenceDataset(train_predictor, train_truth)
    valid_dataset = SequenceDataset(valid_predictor, valid_truth)
    
    return train_dataset, valid_dataset

def train_enc_dec(model, optimizer, dataloader, loss_func = nn.MSELoss()):
    """
    training function 
    
    by default mseloss
    
    could try brier score.
    
    """
    i = 0
    model.train() # enables training for model. 
    tot_loss = 0
    for x, y in dataloader:
#         print("training")
        x = x.to(device) # send to cuda.
        y = y.to(device)
        optimizer.zero_grad() # zeros saved gradients in the optimizer.
        # prevents multiple stacking of gradients
        # this is important to do before we evaluate the model as the 
        # model is currenly in model.train() mode
        
        prediction = model(x) #x should be properly formatted - of size
        """THIS DOESNT DEAL WITH SEQUENCE LENGTH VARIANCE OF PREDICTION OR Y"""
        
#         print("the size of prediction is:", prediction.shape)
        #last image sequence.
        loss = loss_func(prediction, y[:,:1,:,:,:])
#         print(prediction.shape)
#         print(y[:,:1,:,:,:].shape)
        """commented out """
#         loss = - loss_func(prediction[:,0,:,:,:], y[:,0,:,:,:])
    
# ssim_out = -ssim_loss(train[0][0][-1:],  x[0])
# ssim_value = - ssim_out.data
    
    
        
        loss.backward() # differentiates to find minimum.
#         printm()

        ##
        # implement the interpreteable stuff here.
        # as it is very unlikely we predict every pixel correctly we will not 
        # use accuracy. 
        # technically this is a regression problem, not a classification.
        
        
        optimizer.step() # steps forward the optimizer.
        # uses loss.backward() to give gradient. 
        # loss is negative.
#         del x # make sure the garbage is collected.
#         del y
        """commented it out"""
        tot_loss += loss.item() # .data.item() 
        print("BATCH:")
        print(i)
        i += 1
#         if i == 20:
#             break
        print("MSE_LOSS:", tot_loss / i)
    return model # trainloss, trainaccuracy 

def validate(model, dataloader, criterion = nn.MSELoss()):
    """as for train_enc_dec but without training - and acting upon validation
    data set
    """
    model.eval() # puts out of train mode so we do not mess up our gradients
    for x, y in dataloader:
        with torch.no_grad: # no longer have to specify tensors 
            # as volatile = True. as of modern pytorch use torch.no_grad.
            
            x.to(device) # send to cuda.
            y.to(device)
            prediction = model(x)
            
            loss = loss_func(prediction, y)
            
            
    return validloss, validaccuracy





def train_main(model, params, train, valid, epochs = 30, batch_size = 1):
    # make sure model is ported to cuda
    # make sure seed has been specified if testing comparative approaches
    
#     if model.is_cuda == False:
#         model.to(device)
    
    # initialise optimizer on model parameters 
    # chann
    optimizer = torch.optim.Adam(model.parameters(), lr = 0.005)
    loss_func = nn.MSELoss()
#     loss_func = nn.BCELoss()
#     loss_func = pytorch_ssim.SSIM()
    
    train_loader = DataLoader(train, batch_size = batch_size, shuffle = True) # implement moving MNIST data input
    validation_loader = DataLoader(valid, batch_size = batch_size, shuffle = False) # implement moving MNIST
    
    for epoch in range(epochs):
        
        train_enc_dec(model, optimizer, train_loader, loss_func = loss_func) # changed
        
        
        torch.save(optimizer.state_dict(), F"Adam_big_kern3_"+str(epoch)+".pth")
        torch.save(model.state_dict(), F"Test_big_kern3_"+str(epoch)+".pth")
#         validate(model, validation_loader)
        
    return model, optimizer

## now for main activation layer.

if __name__ == "__main__":
    
    
        
    
    