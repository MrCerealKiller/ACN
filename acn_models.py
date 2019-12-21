import numpy as np
from sklearn.neighbors import KNeighborsClassifier
from torch import nn
from torch.nn import functional as F
import torch
from IPython import embed

class ConvEncoder(nn.Module):
    def __init__(self, code_len, input_size=1, encoder_output_size=1000):
        super(ConvEncoder, self).__init__()
        self.code_len = code_len
        self.encoder = nn.Sequential(
            nn.Conv2d(in_channels=input_size,
                      out_channels=16,
                      kernel_size=4,
                      stride=2, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(True),
            nn.Conv2d(in_channels=16,
                      out_channels=16,
                      kernel_size=4,
                      stride=2, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(True),
            nn.Conv2d(in_channels=16,
                      out_channels=16,
                      kernel_size=2,
                      stride=2, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(True),
            nn.Conv2d(in_channels=16,
                      out_channels=code_len*2,
                      kernel_size=1,
                      stride=1, padding=0),
            nn.BatchNorm2d(code_len*2),
            nn.ReLU(True),
           )
        # found via experimentation
        self.eo = eo = encoder_output_size
        self.fc21 = nn.Linear(eo, code_len)
        self.fc22 = nn.Linear(eo, code_len)

    def encode(self, x):
        o = self.encoder(x)
        ol = o.view(o.shape[0], o.shape[1]*o.shape[2]*o.shape[3])
        return self.fc21(ol), self.fc22(ol)

    def reparameterize(self, mu, logvar):
        if self.training:
            std = torch.exp(0.5*logvar)
            eps = torch.randn_like(std)
            o = eps.mul(std).add_(mu)
            return o
        else:
            return mu

    def forward(self, x):
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        return z, mu, logvar

class ConvEncodeDecodeLarge(nn.Module):
    def __init__(self, code_len, input_size=1, output_size=1, encoder_output_size=1000, last_layer_bias=0.5):
        super(ConvEncodeDecodeLarge, self).__init__()
        self.code_len = code_len
        self.encoder_output_size = encoder_output_size
        # find reshape to match encoder --> eo is 4 with mnist (28,28)  and
        # code_len of 64
        self.eo = np.sqrt(encoder_output_size/(2*code_len))
        assert self.eo == int(self.eo)
        self.eo = int(self.eo)

        # architecture dependent
        self.encoder = nn.Sequential(
            nn.Conv2d(in_channels=input_size,
                      out_channels=16,
                      kernel_size=4,
                      stride=2, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(True),
            nn.Conv2d(in_channels=16,
                      out_channels=16,
                      kernel_size=4,
                      stride=2, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(True),
            nn.Conv2d(in_channels=16,
                      out_channels=16,
                      kernel_size=2,
                      stride=2, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(True),
            nn.Conv2d(in_channels=16,
                      out_channels=code_len*2,
                      kernel_size=1,
                      stride=1, padding=0),
            nn.BatchNorm2d(code_len*2),
            nn.ReLU(True),
           )
        # found via experimentation
        n = 16
        self.fc21 = nn.Linear(encoder_output_size, code_len)
        self.fc22 = nn.Linear(encoder_output_size, code_len)
        self.fc3 = nn.Linear(code_len, encoder_output_size)
        self.out_layer = nn.ConvTranspose2d(in_channels=n,
                         out_channels=output_size,
                         kernel_size=1,
                         stride=1, padding=0)

        # set bias to 0.5 for sigmoid with bce - 0 when using dml
        self.out_layer.bias.data.fill_(last_layer_bias)

        self.decoder = nn.Sequential(
                # 4x4
                nn.ConvTranspose2d(in_channels=code_len*2,
                       out_channels=n,
                       kernel_size=1,
                       stride=1, padding=0),
                 nn.BatchNorm2d(n),
                 nn.ReLU(True),
                 # 4x4 -->  8x8
                 nn.ConvTranspose2d(in_channels=n,
                       out_channels=n,
                       kernel_size=4,
                       stride=2, padding=1),
                 nn.BatchNorm2d(n),
                 nn.ReLU(True),
                 # 8>14
                 nn.ConvTranspose2d(in_channels=n,
                         out_channels=n,
                         kernel_size=2,
                         stride=2, padding=1),
                 nn.BatchNorm2d(16),
                 nn.ReLU(True),
                 # 14->28
                 nn.ConvTranspose2d(in_channels=n,
                         out_channels=n,
                         kernel_size=2,
                         stride=2, padding=0),
                 nn.BatchNorm2d(n),
                 nn.ReLU(True),
                self.out_layer,
                )


    def encode(self, x):
        o = self.encoder(x)
        ol = o.view(o.shape[0], o.shape[1]*o.shape[2]*o.shape[3])
        return self.fc21(ol), self.fc22(ol)

    def decode(self, z):
        co = F.relu(self.fc3(z))
        col = co.view(co.shape[0], self.code_len*2, self.eo, self.eo)
        do = self.decoder(col)
        return do

    def reparameterize(self, mu, logvar):
        if self.training:
            std = torch.exp(0.5*logvar)
            eps = torch.randn_like(std)
            o = eps.mul(std).add_(mu)
            return o
        else:
            return mu

    def forward(self, x):
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        return self.decode(z), z, mu, logvar

class ConvEncodeDecode(nn.Module):
    def __init__(self, code_len, input_size=1, output_size=1, encoder_output_size=1000, last_layer_bias=0.5):
        super(ConvEncodeDecode, self).__init__()
        self.code_len = code_len
        # find reshape to match encoder --> eo is 4 with mnist (28,28)  and
        # code_len of 64
        # eo should be 7 for mnist
        self.eo = np.sqrt(encoder_output_size/(2*code_len))
        assert self.eo == int(self.eo)
        self.eo = int(self.eo)
        # architecture dependent
        self.encoder = nn.Sequential(
            nn.Conv2d(in_channels=input_size,
                      out_channels=16,
                      kernel_size=4,
                      stride=2, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(True),
            nn.Conv2d(in_channels=16,
                      out_channels=32,
                      kernel_size=4,
                      stride=2, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(True),
            nn.Conv2d(in_channels=32,
                      out_channels=code_len*2,
                      kernel_size=1,
                      stride=1, padding=0),
            nn.BatchNorm2d(code_len*2),
            nn.ReLU(True),
           )
        self.fc21 = nn.Linear(encoder_output_size, code_len)
        self.fc22 = nn.Linear(encoder_output_size, code_len)
        self.fc3 = nn.Linear(code_len, encoder_output_size)

        self.out_layer = nn.ConvTranspose2d(in_channels=16,
                        out_channels=output_size,
                        kernel_size=4,
                        stride=2, padding=1)

        # set bias to 0.5 for sigmoid with bce - 0 when using dml
        self.out_layer.bias.data.fill_(last_layer_bias)

        self.decoder = nn.Sequential(
               nn.ConvTranspose2d(in_channels=code_len*2,
                      out_channels=32,
                      kernel_size=1,
                      stride=1, padding=0),
                nn.BatchNorm2d(32),
                nn.ReLU(True),
                nn.ConvTranspose2d(in_channels=32,
                      out_channels=16,
                      kernel_size=4,
                      stride=2, padding=1),
                nn.BatchNorm2d(16),
                nn.ReLU(True),
                self.out_layer
                     )

    def encode(self, x):
        o = self.encoder(x)
        ol = o.view(o.shape[0], o.shape[1]*o.shape[2]*o.shape[3])
        return self.fc21(ol), self.fc22(ol)

    def decode(self, z):
        co = F.relu(self.fc3(z))
        col = co.view(co.shape[0], self.code_len*2, self.eo, self.eo)
        do = self.decoder(col)
        return do

    def reparameterize(self, mu, logvar):
        if self.training:
            std = torch.exp(0.5*logvar)
            eps = torch.randn_like(std)
            o = eps.mul(std).add_(mu)
            return o
        else:
            return mu

    def forward(self, x):
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        return self.decode(z), z, mu, logvar

class Upsample(nn.Module):
    def __init__(self, input_size=1, output_size=1):
        super(Upsample, self).__init__()
        """"
        test code to upsample forcibly downsampled image for spatial conditioning
        expects image of size bs,x,7,7 and will output bs,x,28,28
        """
        self.eo = 7
        n = 16
        self.out_layer = nn.ConvTranspose2d(in_channels=n,
                        out_channels=output_size,
                        kernel_size=4,
                        stride=2, padding=1)

        self.upsample = nn.Sequential(
               nn.ConvTranspose2d(in_channels=input_size,
                      out_channels=n,
                      kernel_size=1,
                      stride=1, padding=0),
                nn.BatchNorm2d(n),
                nn.ReLU(True),
                nn.ConvTranspose2d(in_channels=n,
                      out_channels=n,
                      kernel_size=4,
                      stride=2, padding=1),
                nn.BatchNorm2d(n),
                nn.ReLU(True),
                self.out_layer
                     )

    def forward(self, x):
        return self.upsample(x)





class PriorNetwork(nn.Module):
    def __init__(self, size_training_set, code_length, n_hidden=512, k=5, random_seed=4543):
        super(PriorNetwork, self).__init__()
        self.rdn = np.random.RandomState(random_seed)
        self.k = k
        self.size_training_set = size_training_set
        self.code_length = code_length
        self.fc1 = nn.Linear(self.code_length, n_hidden)
        self.fc2_u = nn.Linear(n_hidden, self.code_length)
        self.fc2_s = nn.Linear(n_hidden, self.code_length)

        self.knn = KNeighborsClassifier(n_neighbors=self.k, n_jobs=-1)
        # codes are initialized randomly - Alg 1: initialize C: c(x)~N(0,1)
        codes = self.rdn.standard_normal((self.size_training_set, self.code_length))
        self.fit_knn(codes)

    def fit_knn(self, codes):
        ''' will reset the knn  given an nd array
        '''
        self.codes = codes
        y = np.zeros((len(self.codes)))
        self.knn.fit(self.codes, y)

    def batch_pick_close_neighbor(self, codes):
        '''
        :code latent activation of training example as np
        '''
        neighbor_distances, neighbor_indexes = self.knn.kneighbors(codes, n_neighbors=self.k, return_distance=True)
        bsize = neighbor_indexes.shape[0]
        if self.training:
            # randomly choose neighbor index from top k
            chosen_neighbor_index = self.rdn.randint(0,neighbor_indexes.shape[1],size=bsize)
        else:
            chosen_neighbor_index = np.zeros((bsize), dtype=np.int)
        return self.codes[neighbor_indexes[np.arange(bsize), chosen_neighbor_index]]

    def forward(self, codes):
        device = codes.device
        np_codes = codes.cpu().detach().numpy()
        previous_codes = self.batch_pick_close_neighbor(np_codes)
        previous_codes = torch.FloatTensor(previous_codes).to(device)
        return self.encode(previous_codes)

    def encode(self, prev_code):
        h1 = F.relu(self.fc1(prev_code))
        mu = self.fc2_u(h1)
        logstd = self.fc2_s(h1)
        return mu, logstd


