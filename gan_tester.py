#%%

from __future__ import print_function
#%matplotlib inline
import os
import random
import torch
import torch.nn as nn
import torch.optim as optim
import torch.utils.data
import torchvision.datasets as dset
import torchvision.transforms as transforms
import torchvision.utils as vutils
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from IPython.display import HTML

import dataloader


# Set random seed for reproducibility
manualSeed = 999
print("Random Seed: ", manualSeed)
random.seed(manualSeed)
torch.manual_seed(manualSeed)

#%%

# Dataset path
HOME = os.path.expanduser('~')
dataroot = HOME + '/Datasets/celeba/'

# Hyperparameters
workers = 8
batch_size = 64
image_size = 64
num_epochs = 100
lr = 0.0002
beta1 = 0.5
nc = 3  # Number of channels
nz = 100  # Size of z latent vector
ngf = 64  # Size of feature maps in generator
ndf = 16  # # Size of feature maps in discriminator

#%%

# Create the dataset
# dataset = dset.ImageFolder(root=dataroot,
#                            transform=transforms.Compose([
#                                transforms.Resize(image_size),
#                                transforms.CenterCrop(image_size),
#                                transforms.ToTensor(),
#                                transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
#                            ]))

ds = dataloader.RAVDESSDSPix2Pix(HOME + '/Datasets/RAVDESS/LandmarksLineImage128',
                                 HOME + '/Datasets/RAVDESS/Image128',
                                 'image',
                                 use_same_sentence=True,
                                 normalize=False,
                                 mean=[0.755, 0.673, 0.652],
                                 std=[0.300, 0.348, 0.361],
                                 max_samples=None,
                                 seed=123,
                                 sequence_length=1,
                                 step_size=1,
                                 image_size=64)

print("Found {} samples in total".format(len(ds)))

# Create the dataloader
dataloader = torch.utils.data.DataLoader(ds, batch_size=batch_size,
                                         shuffle=True, num_workers=workers)


# Decide which device we want to run on
device = torch.device("cuda" if (torch.cuda.is_available()) else "cpu")

print("Training on {}".format(device))

#%%

# Plot some training images
real_batch = next(iter(dataloader))
plt.figure(figsize=(8, 8))
plt.axis("off")
plt.title("Training Images")
plt.imshow(np.transpose(vutils.make_grid(real_batch['B'][:, 0].to(device)[:64], padding=2, normalize=True).cpu(),(1,2,0)))
plt.savefig("Training_images.png")

#%%


# custom weights initialization called on netG and netD
def weights_init(m):
    classname = m.__class__.__name__
    if classname.find('Conv') != -1:
        nn.init.normal_(m.weight.data, 0.0, 0.02)
    elif classname.find('BatchNorm') != -1:
        nn.init.normal_(m.weight.data, 1.0, 0.02)
        nn.init.constant_(m.bias.data, 0)


# Generator
class Generator(nn.Module):
    def __init__(self):
        super(Generator, self).__init__()

        self.g = NoiseGenerator()

    def forward(self, x):
        """
        x.shape -> [b, sequence_length, c, h, w]
        cond.shape -> [b, 1]

        args:
            x (torch.tensor): input sequence
            cond(torch.tensor): conditioning label
        """
        y = []
        for idx in range(x.size(1)):
            y.append(self.g(x[:, idx]))
        y = torch.stack(y, dim=1)
        return y


class NoiseGenerator(nn.Module):
    def __init__(self, n_features=64, n_latent=100):
        super(NoiseGenerator, self).__init__()

        nc = 3
        self.n_latent = n_latent

        self.main = nn.Sequential(
            # input is Z, going into a convolution
            nn.ConvTranspose2d(n_latent, n_features * 8, 4, 1, 0, bias=False),
            nn.BatchNorm2d(n_features * 8),
            nn.ReLU(True),
            # state size. (n_features*8) x 4 x 4
            nn.ConvTranspose2d(n_features * 8, n_features * 4, 4, 2, 1, bias=False),
            nn.BatchNorm2d(n_features * 4),
            nn.ReLU(True),
            # state size. (n_features*4) x 8 x 8
            nn.ConvTranspose2d(n_features * 4, n_features * 2, 4, 2, 1, bias=False),
            nn.BatchNorm2d(n_features * 2),
            nn.ReLU(True),
            # state size. (n_features*2) x 16 x 16
            nn.ConvTranspose2d(n_features * 2, n_features, 4, 2, 1, bias=False),
            nn.BatchNorm2d(n_features),
            nn.ReLU(True),
            # state size. (n_features) x 32 x 32
            nn.ConvTranspose2d(n_features, nc, 4, 2, 1, bias=False),
            nn.Tanh()
            # state size. (nc) x 64 x 64
        )

    def forward(self, x):
        noise = torch.randn(x.size(0), self.n_latent, 1, 1, device=x.device)
        return self.main(noise)


# Discriminator
class Discriminator(nn.Module):
    def __init__(self, n_features=16):
        super(Discriminator, self).__init__()

        nc = 3

        self.model = nn.Sequential(
            # input is (nc) x 64 x 64
            nn.Conv2d(nc, n_features, 4, 2, 1, bias=False),
            nn.LeakyReLU(0.2, inplace=True),
            # state size. (n_features) x 32 x 32
            nn.Conv2d(n_features, n_features * 2, 4, 2, 1, bias=False),
            nn.BatchNorm2d(n_features * 2),
            nn.LeakyReLU(0.2, inplace=True),
            # state size. (n_features*2) x 16 x 16
            nn.Conv2d(n_features * 2, n_features * 4, 4, 2, 1, bias=False),
            nn.BatchNorm2d(n_features * 4),
            nn.LeakyReLU(0.2, inplace=True),
            # state size. (n_features*4) x 8 x 8
            nn.Conv2d(n_features * 4, n_features * 8, 4, 2, 1, bias=False),
            nn.BatchNorm2d(n_features * 8),
            nn.LeakyReLU(0.2, inplace=True),
            # state size. (n_features*8) x 4 x 4
            nn.Conv2d(n_features * 8, 1, 4, 1, 0, bias=False),
            nn.Sigmoid()
        )

    def forward(self, img):
        out = []
        for i_seq in range(img.size(1)):
            out.append(self.model(img[:, i_seq]))
        out = torch.stack(out, 1)

        return out


#%%

# Init generator and discriminator
netG = Generator().to(device)
netG.apply(weights_init)

netD = Discriminator().to(device)
netD.apply(weights_init)

#%%

# Initialize BCELoss function
criterion = nn.BCELoss()

# Create batch of latent vectors that we will use to visualize
#  the progression of the generator
fixed_noise = torch.randn(64, nz, 1, 1, device=device)

# Establish convention for real and fake labels during training
real_label = 1
fake_label = 0

# Setup Adam optimizers for both G and D
optimizerD = optim.Adam(netD.parameters(), lr=lr, betas=(beta1, 0.999))
optimizerG = optim.Adam(netG.parameters(), lr=lr, betas=(beta1, 0.999))

#%%

# Training Loop

# Lists to keep track of progress
img_list = []
G_losses = []
D_losses = []
iters = 0

print("Starting Training Loop...")
# For each epoch
for epoch in range(num_epochs):
    # For each batch in the dataloader
    for i, data in enumerate(dataloader, 0):

        ############################
        # (1) Update D network: maximize log(D(x)) + log(1 - D(G(z)))
        ###########################
        ## Train with all-real batch
        netD.zero_grad()
        # Format batch
        real_cpu = data['B'].to(device)
        b_size = real_cpu.size(0)
        label = torch.full((b_size,), real_label, device=device)
        # Forward pass real batch through D
        output = netD(real_cpu).view(-1)
        # Calculate loss on all-real batch
        errD_real = criterion(output, label)
        # Calculate gradients for D in backward pass
        errD_real.backward()
        D_x = output.mean().item()

        ## Train with all-fake batch
        # Generate batch of latent vectors
        # noise = torch.randn(b_size, nz, 1, 1, device=device)
        noise = torch.randn(b_size, real_cpu.size(1), 1, 1, device=device)
        # Generate fake image batch with G
        fake = netG(noise)
        label.fill_(fake_label)
        # Classify all fake batch with D
        output = netD(fake.detach()).view(-1)
        # Calculate D's loss on the all-fake batch
        errD_fake = criterion(output, label)
        # Calculate the gradients for this batch
        errD_fake.backward()
        D_G_z1 = output.mean().item()
        # Add the gradients from the all-real and all-fake batches
        errD = 0.5 * (errD_real + errD_fake)
        # Update D
        optimizerD.step()

        ############################
        # (2) Update G network: maximize log(D(G(z)))
        ###########################
        netG.zero_grad()
        label.fill_(real_label)  # fake labels are real for generator cost
        # Since we just updated D, perform another forward pass of all-fake batch through D
        output = netD(fake).view(-1)
        # Calculate G's loss based on this output
        errG = criterion(output, label)
        # Calculate gradients for G
        errG.backward()
        D_G_z2 = output.mean().item()
        # Update G
        optimizerG.step()

        # Output training stats
        if i % 50 == 0:
            print('[%d/%d][%d/%d]\tLoss_D: %.4f\tLoss_G: %.4f\tD(x): %.4f\tD(G(z)): %.4f / %.4f'
                  % (epoch, num_epochs, i, len(dataloader),
                     errD.item(), errG.item(), D_x, D_G_z1, D_G_z2))

        # Save Losses for plotting later
        G_losses.append(errG.item())
        D_losses.append(errD.item())

        # Check how the generator is doing by saving G's output on fixed_noise
        if (iters % 500 == 0) or ((epoch == num_epochs-1) and (i == len(dataloader)-1)):
            with torch.no_grad():
                fake = netG(fixed_noise).detach().cpu()
            img_list.append(vutils.make_grid(fake, padding=2, normalize=True))

        iters += 1

#%%

# Plot loss
plt.figure(figsize=(10, 5))
plt.title("Generator and Discriminator Loss During Training")
plt.plot(G_losses, label="G")
plt.plot(D_losses, label="D")
plt.xlabel("iterations")
plt.ylabel("Loss")
plt.legend()
# plt.show()
plt.savefig('losses.png')

#%%

# Show images
# fig = plt.figure(figsize=(8,v8))
# plt.axis("off")
# ims = [[plt.imshow(np.transpose(i, (1, 2, 0)), animated=True)] for i in img_list]
# ani = animation.ArtistAnimation(fig, ims, interval=1000, repeat_delay=1000, blit=True)
#
# HTML(ani.to_jshtml())

#%%

# Real images vs fake images
real_batch = next(iter(dataloader))

# Plot the real images
plt.figure(figsize=(15, 15))
plt.subplot(1, 2, 1)
plt.axis("off")
plt.title("Real Images")
plt.imshow(np.transpose(vutils.make_grid(real_batch['B'][:, 0].to(device)[:64], padding=5, normalize=True).cpu(),(1,2,0)))

# Plot the fake images from the last epoch
plt.subplot(1, 2, 2)
plt.axis("off")
plt.title("Fake Images")
plt.imshow(np.transpose(img_list[-1], (1, 2, 0)))
# plt.show()
plt.savefig('real_and_fake.png')
