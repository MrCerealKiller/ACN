import numpy as np
from sklearn.neighbors import KNeighborsClassifier
from torch import nn
from torch.nn import functional as F
import torch
from IPython import embed
# fast vq from rithesh
from functions import vq, vq_st
def weights_init(m):
    classname = m.__class__.__name__
    if classname.find('Conv') != -1:
        try:
            nn.init.xavier_uniform_(m.weight.data)
            m.bias.data.fill_(0)
        except AttributeError:
            print("Skipping initialization of ", classname)

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


class ConvEncodeDecodeLargeVQVAE(nn.Module):
    def __init__(self, code_len, input_size=1, output_size=1,
                       encoder_output_size=1000, last_layer_bias=0.5, num_clusters=512, num_z=32):
        super(ConvEncodeDecodeLargeVQVAE, self).__init__()
        self.code_len = code_len
        self.encoder_output_size = encoder_output_size
        self.num_clusters = num_clusters
        self.num_z = num_z
        self.eo = np.sqrt(encoder_output_size/code_len)
        assert self.eo == int(self.eo)
        self.eo = int(self.eo)
        # code_len of 64
        n = 16
        # architecture dependent
        self.encoder = nn.Sequential(
            nn.Conv2d(in_channels=input_size,
                      out_channels=n,
                      kernel_size=4,
                      stride=2, padding=1),
            nn.BatchNorm2d(n),
            nn.ReLU(True),
            nn.Conv2d(in_channels=n,
                      out_channels=n,
                      kernel_size=4,
                      stride=2, padding=1),
            nn.BatchNorm2d(n),
            nn.ReLU(True),
            nn.Conv2d(in_channels=n,
                      out_channels=n,
                      kernel_size=2,
                      stride=2, padding=1),
            nn.BatchNorm2d(n),
            nn.ReLU(True),
            nn.Conv2d(in_channels=n,
                      out_channels=num_z,
                      kernel_size=1,
                      stride=1, padding=0),
            nn.BatchNorm2d(num_z),
            nn.ReLU(True),
           )

        self.fc21 = nn.Linear(encoder_output_size, code_len)
        self.fc22 = nn.Linear(encoder_output_size, code_len)
        self.fc3 = nn.Linear(code_len, encoder_output_size)
        self.conv_layers = nn.Sequential(
                               nn.ConvTranspose2d(in_channels=self.code_len,
                                  out_channels=num_z,
                                  kernel_size=1,
                                  stride=1, padding=0),
                               nn.BatchNorm2d(num_z),
                               nn.ReLU(True),
                               nn.ConvTranspose2d(in_channels=num_z,
                                  out_channels=num_z,
                                  kernel_size=1,
                                  stride=1, padding=0),
                               )

        self.out_layer = nn.ConvTranspose2d(in_channels=n,
                         out_channels=output_size,
                         kernel_size=1,
                         stride=1, padding=0)

        # set bias to 0.5 for sigmoid with bce - 0 when using dml
        self.out_layer.bias.data.fill_(last_layer_bias)
        ## vq embedding scheme
        #self.embedding = nn.Embedding(num_clusters, num_z)
        # common scaling for embeddings - variance roughly scales with num_clusters
        #self.embedding.weight.data.copy_(1./num_clusters * torch.randn(num_clusters, num_z))
        # from Rithesh
        self.codebook = VQEmbedding(num_clusters, num_z)

        self.decoder = nn.Sequential(
                # 4x4
                nn.ConvTranspose2d(in_channels=num_z,
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
                 nn.BatchNorm2d(n),
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
        self.apply(weights_init)

    def reparameterize(self, mu, logvar):
        if self.training:
            std = torch.exp(0.5*logvar)
            eps = torch.randn_like(std)
            o = eps.mul(std).add_(mu)
            return o
        else:
            return mu

    def acn_encode(self, x):
        o = self.encoder(x)
        ol = o.view(o.shape[0], o.shape[1]*o.shape[2]*o.shape[3])
        mu = self.fc21(ol)
        logvar =self.fc22(ol)
        z = self.reparameterize(mu, logvar)
        return z, mu, logvar

    def vq_encode(self, z):
        # convert z to image shape
        co = F.relu(self.fc3(z))
        co = co.view(z.shape[0], self.code_len, self.eo, self.eo)
        z_e_x = self.conv_layers(co)
        latents = self.codebook(z_e_x)
        return z_e_x, latents

    def decode(self, latents):
        z_q_x = self.codebook.embedding(latents).permute(0, 3, 1, 2)  # (B, D, H, W)
        x_tilde = self.decoder(z_q_x)
        return x_tilde, z_q_x

    def forward(self, x):
        z, mu, logvar = self.acn_encode(x)
        z_e_x, latents = self.vq_encode(z)
        z_q_x_st, z_q_x = self.codebook.straight_through(z_e_x)
        x_tilde = self.decoder(z_q_x_st)
        return x_tilde, z, mu, logvar, z_e_x, z_q_x, latents

class VQEmbedding(nn.Module):
    def __init__(self, K, D):
        super().__init__()
        self.embedding = nn.Embedding(K, D)
        self.embedding.weight.data.uniform_(-1./K, 1./K)

    def forward(self, z_e_x):
        z_e_x_ = z_e_x.permute(0, 2, 3, 1).contiguous()
        latents = vq(z_e_x_, self.embedding.weight)
        return latents

    def straight_through(self, z_e_x):
        z_e_x_ = z_e_x.permute(0, 2, 3, 1).contiguous()
        z_q_x_, indices = vq_st(z_e_x_, self.embedding.weight.detach())
        z_q_x = z_q_x_.permute(0, 3, 1, 2).contiguous()

        z_q_x_bar_flatten = torch.index_select(self.embedding.weight,
            dim=0, index=indices)
        z_q_x_bar_ = z_q_x_bar_flatten.view_as(z_e_x_)
        z_q_x_bar = z_q_x_bar_.permute(0, 3, 1, 2).contiguous()

        return z_q_x, z_q_x_bar

# rithesh version
# https://github.com/ritheshkumar95/pytorch-vqvae/blob/master/vqvae.py
class ResBlock(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.block = nn.Sequential(
            nn.ReLU(True),
            nn.Conv2d(dim, dim, 3, 1, 1),
            nn.BatchNorm2d(dim),
            nn.ReLU(True),
            nn.Conv2d(dim, dim, 1),
            nn.BatchNorm2d(dim)
        )

    def forward(self, x):
        return x + self.block(x)

class VQVAEres(nn.Module):
    def __init__(self, input_size=1, output_size=1, hidden_size=256,
                       last_layer_bias=0.5, num_clusters=512, num_z=32):

        super(VQVAEres, self).__init__()
        self.num_clusters = num_clusters
        self.num_z = num_z
        self.hidden_size = hidden_size
        self.encoder = nn.Sequential(
            nn.Conv2d(input_size, hidden_size, 4, 2, 1),
            nn.BatchNorm2d(hidden_size),
            nn.ReLU(True),
            nn.Conv2d(hidden_size, hidden_size, 4, 2, 1),
            ResBlock(hidden_size),
            ResBlock(hidden_size),
            )
        self.codebook = VQEmbedding(num_clusters, hidden_size)
        self.decoder = nn.Sequential(
                  ResBlock(hidden_size),
                  ResBlock(hidden_size),
                  nn.ConvTranspose2d(hidden_size, hidden_size, 4, 2, 1),
                  nn.BatchNorm2d(hidden_size),
                  nn.ReLU(True),
                  nn.ConvTranspose2d(hidden_size, output_size, 4, 2, 1),
                  )
        self.apply(weights_init)

    def encode(self, x):
        z_e_x = self.encoder(x)
        latents = self.codebook(z_e_x)
        return z_e_x, latents

    def decode(self, latents):
        # TODO order/?
        z_q_x = self.codebook.embedding(latents).permute(0,3,1,2) # BDHW
        x_tilde = self.decoder(z_q_x)
        return x_tilde, z_q_x

    def forward(self, x):
        z_e_x, latents = self.encode(x)
        z_q_x_st, z_q_x = self.codebook.straight_through(z_e_x)
        x_tilde = self.decoder(z_q_x_st)
        return x_tilde, z_e_x, z_q_x, latents

class ACNVQVAEres(nn.Module):
    def __init__(self, code_len, input_size=1, output_size=1, encoder_output_size=1024,
                       hidden_size=256,
                       num_clusters=512, num_z=32):

        super(ACNVQVAEres, self).__init__()
        self.code_len = code_len
        self.num_clusters = num_clusters
        self.num_z = num_z
        self.hidden_size = hidden_size
        # encoder output size found experimentally when architecture changes
        self.encoder_output_size = encoder_output_size
        self.eo = 7

        self.encoder = nn.Sequential(
            nn.Conv2d(input_size, hidden_size, 4, 2, 1),
            nn.BatchNorm2d(hidden_size),
            nn.ReLU(True),
            nn.Conv2d(hidden_size, hidden_size, 4, 2, 1),
            ResBlock(hidden_size),
            ResBlock(hidden_size),
            # code len is arbitrary bottleneck
            nn.Conv2d(hidden_size, 16, 1, 1, 0),
            )
        self.fc21 = nn.Linear(self.encoder_output_size, code_len)
        self.fc22 = nn.Linear(self.encoder_output_size, code_len)
        self.fc3 = nn.Linear(code_len, self.encoder_output_size)
        self.conv_layers = nn.Sequential(
            nn.Conv2d(16, hidden_size, 1, 1, 0),
            nn.BatchNorm2d(hidden_size),
            nn.ReLU(True),
            nn.Conv2d(hidden_size, hidden_size, 1, 1, 0),
            ResBlock(hidden_size),
            nn.Conv2d(hidden_size, hidden_size, 1, 1, 0),
            )
        self.codebook = VQEmbedding(num_clusters, hidden_size)
        self.decoder = nn.Sequential(
                  ResBlock(hidden_size),
                  ResBlock(hidden_size),
                  nn.ConvTranspose2d(hidden_size, hidden_size, 4, 2, 1),
                  nn.BatchNorm2d(hidden_size),
                  nn.ReLU(True),
                  nn.ConvTranspose2d(hidden_size, output_size, 4, 2, 1),
                  )
        self.apply(weights_init)

    def reparameterize(self, mu, logvar):
        if self.training:
            std = torch.exp(0.5*logvar)
            eps = torch.randn_like(std)
            o = eps.mul(std).add_(mu)
            return o
        else:
            return mu

    def acn_encode(self, x):
        o = self.encoder(x)
        # output is 84,256,7,7 for mnist
        o = o.view(o.shape[0], o.shape[1]*o.shape[2]*o.shape[3])
        mu = self.fc21(o)
        logvar =self.fc22(o)
        z = self.reparameterize(mu, logvar)
        return z, mu, logvar

    def vq_encode(self, z):
        # convert z to image shape
        co = F.relu(self.fc3(z))
        co = co.view(z.shape[0], 16, 7, 7)
        z_e_x = self.conv_layers(co)
        latents = self.codebook(z_e_x)
        return z_e_x, latents

    def forward(self, x):
        z, mu, logvar = self.acn_encode(x)
        z_e_x, latents = self.vq_encode(z)
        z_q_x_st, z_q_x = self.codebook.straight_through(z_e_x)
        x_tilde = self.decoder(z_q_x_st)
        return x_tilde, z, mu, logvar, z_e_x, z_q_x, latents


class VQVAE(nn.Module):
     # reconstruction from this model is poor
    def __init__(self, input_size=1, output_size=1,
                       encoder_output_size=1000, last_layer_bias=0.5, num_clusters=512, num_z=32):
        super(VQVAE, self).__init__()
        self.encoder_output_size = encoder_output_size
        self.num_clusters = num_clusters
        self.num_z = num_z
        n = 16
        # architecture dependent
        self.encoder = nn.Sequential(
            nn.Conv2d(in_channels=input_size,
                      out_channels=n,
                      kernel_size=4,
                      stride=2, padding=1),
            nn.BatchNorm2d(n),
            nn.ReLU(True),
            nn.Conv2d(in_channels=n,
                      out_channels=n,
                      kernel_size=4,
                      stride=2, padding=1),
            nn.BatchNorm2d(n),
            nn.ReLU(True),
            nn.Conv2d(in_channels=n,
                      out_channels=n,
                      kernel_size=2,
                      stride=2, padding=1),
            nn.BatchNorm2d(n),
            nn.ReLU(True),
            nn.Conv2d(in_channels=n,
                      out_channels=num_z,
                      kernel_size=1,
                      stride=1, padding=0),
            nn.BatchNorm2d(num_z),
            nn.ReLU(True),
           )

        self.out_layer = nn.ConvTranspose2d(in_channels=n,
                         out_channels=output_size,
                         kernel_size=1,
                         stride=1, padding=0)

        # set bias to 0.5 for sigmoid with bce - 0 when using dml
        self.out_layer.bias.data.fill_(last_layer_bias)
        ## vq embedding scheme
        #self.embedding = nn.Embedding(num_clusters, num_z)
        # common scaling for embeddings - variance roughly scales with num_clusters
        #self.embedding.weight.data.copy_(1./num_clusters * torch.randn(num_clusters, num_z))
        # from Rithesh
        self.codebook = VQEmbedding(num_clusters, num_z)

        self.decoder = nn.Sequential(
                # 4x4
                nn.ConvTranspose2d(in_channels=num_z,
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
                 nn.BatchNorm2d(n),
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
        self.apply(weights_init)

    def encode(self, x):
        z_e_x = self.encoder(x)
        latents = self.codebook(z_e_x)
        return z_e_x, latents

    def decode(self, latents):
        z_q_x = self.codebook.embedding(latents).permute(0, 3, 1, 2)  # (B, D, H, W)
        x_tilde = self.decoder(z_q_x)
        return x_tilde, z_q_x

    def forward(self, x):
        z_e_x, latents = self.encode(x)
        z_q_x_st, z_q_x = self.codebook.straight_through(z_e_x)
        x_tilde = self.decoder(z_q_x_st)
        return x_tilde, z_e_x, z_q_x, latents


#    def vq_decode(self, z_e_x):
#        # NCHW is the order in the encoder
#        # (num, channels, height, width)
#        N, C, H, W = z_e_x.shape
#        # need NHWC instead of default NCHW for easier computations
#        z_e_x_transposed = z_e_x.permute(0,2,3,1)
#        # needs C,K
#        emb = self.embedding.weight.transpose(0,1)
#        # broadcast to determine distance from encoder output to clusters
#        # NHWC -> NHWCK
#        measure = z_e_x_transposed.unsqueeze(4) - emb[None, None, None]
#        # num_clusters=512, num_z=64
#        # measure is of shape bs,10,10,64,512
#        # square each element, then sum over channels
#        # take sum over each z - find min
#        dists = torch.pow(measure, 2).sum(-2)
#        # pytorch gives real min and arg min - select argmin
#        # this is the closest k for each sample - Equation 1
#        # latents is a array of integers
#        # mnist latents are size bs,4,4
#        latents = dists.min(-1)[1]
#        # look up cluster centers
#        x_tilde, z_q_x = self.decode_clusters(latents, N, H, W, C)
#        return x_tilde, z_q_x, latents
#
#    def decode_clusters(self, latents, N, H, W, C):
#        z_q_x = self.embedding(latents.view(latents.shape[0], -1))
#        # back to NCHW (orig) - now cluster centers/class
#        z_q_x = z_q_x.view(N, H, W, C).permute(0, 3, 1, 2)
#        # put quantized data through decoder
#        x_tilde = self.decoder(z_q_x)
#        return x_tilde, z_q_x



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


