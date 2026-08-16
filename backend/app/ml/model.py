"""SalGAN-style saliency generator.

ARCHITECTURE IS LOCKED (BUILD.md section 3). Do not modify: any change to layer
shapes or naming breaks ``load_state_dict(..., strict=True)`` against the
trained ``stage3_ui_best_val.pth`` checkpoint.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision


def _vgg16_features(pretrained=False):
    return torchvision.models.vgg16(weights=None).features


class _DecoderBlock(nn.Module):
    def __init__(self, in_ch, out_ch):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1), nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1), nn.ReLU(inplace=True))

    def forward(self, x, skip):
        x = F.interpolate(x, scale_factor=2, mode="bilinear", align_corners=False)
        return self.conv(torch.cat([x, skip], dim=1))


class SalGANGenerator(nn.Module):
    """SalGAN-style encoder-decoder, VGG16 encoder + U-Net skip connections.
    Outputs 1-channel LOGITS at input resolution (apply sigmoid for a map)."""
    def __init__(self, pretrained=False):
        super().__init__()
        vgg = _vgg16_features(pretrained)
        self.enc1, self.pool1 = vgg[0:4],  vgg[4]
        self.enc2, self.pool2 = vgg[5:9],  vgg[9]
        self.enc3, self.pool3 = vgg[10:16], vgg[16]
        self.enc4, self.pool4 = vgg[17:23], vgg[23]
        self.enc5 = vgg[24:30]
        self.dec4 = _DecoderBlock(512 + 512, 512)
        self.dec3 = _DecoderBlock(512 + 256, 256)
        self.dec2 = _DecoderBlock(256 + 128, 128)
        self.dec1 = _DecoderBlock(128 + 64, 64)
        self.out = nn.Conv2d(64, 1, 1)

    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool1(e1))
        e3 = self.enc3(self.pool2(e2))
        e4 = self.enc4(self.pool3(e3))
        e5 = self.enc5(self.pool4(e4))
        d = self.dec4(e5, e4)
        d = self.dec3(d, e3)
        d = self.dec2(d, e2)
        d = self.dec1(d, e1)
        return self.out(d)
