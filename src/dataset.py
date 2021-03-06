import xml.etree.ElementTree as ET
import glob2
import torch
import numpy as np

from torch.utils.data import Dataset
import cv2

from src.config import OPEN_IMAGES_CLASSES


class OpenImagesDataset(Dataset):
    def __init__(self, root_dir='data', class_names=OPEN_IMAGES_CLASSES, set_name='train', transform=None):
        self.root_dir = root_dir
        self.set_name = set_name
        self.transform = transform
        self.class_names = class_names

        self.images = []
        self.image_to_category_name = {}

        self.load_images()

    def load_images(self):
        for c in self.class_names:
            meta_files = glob2.glob(f"{self.root_dir}/{self.set_name}/{c}/images/*jpg")
            for f in meta_files:
                self.images.append(f[-20:-4])
                self.image_to_category_name[f[-20:-4]] = c

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        img = self.get_image(idx)
        annot = self.get_annotations(idx)
        sample = {'img': img, 'annot': annot}

        if self.transform:
            sample = self.transform(sample)

        return sample

    def get_image(self, idx):
        path = f'{self.root_dir}/{self.set_name}/{self.image_to_category_name[self.images[idx]]}/images/{self.images[idx]}.jpg'
        img = cv2.imread(path)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        return img.astype(np.float32) / 255.

    def get_annotations(self, idx):
        class_name = self.image_to_category_name[self.images[idx]]
        path = f'{self.root_dir}/{self.set_name}/{class_name}/pascal/{self.images[idx]}.xml'

        tree = ET.parse(path)
        root = tree.getroot()

        annotations = np.zeros((0, 5))
        for obj in root.findall('object'):
            x1 = int(obj.find('bndbox').find('xmin').text)
            x2 = int(obj.find('bndbox').find('xmax').text)
            y1 = int(obj.find('bndbox').find('ymin').text)
            y2 = int(obj.find('bndbox').find('ymax').text)
            annotation = np.zeros((1, 5))
            annotation[0, :4] = [x1, y1, x2, y2]
            annotation[0, 4] = self.class_names.index(class_name)
            annotations = np.append(annotations, annotation, axis=0)

        return annotations

    def num_classes(self):
        return len(self.class_names)


def collater(data):
    imgs = [s['img'] for s in data]
    annots = [s['annot'] for s in data]
    scales = [s['scale'] for s in data]

    imgs = torch.from_numpy(np.stack(imgs, axis=0))

    max_num_annots = max(annot.shape[0] for annot in annots)

    if max_num_annots > 0:

        annot_padded = torch.ones((len(annots), max_num_annots, 5)) * -1

        if max_num_annots > 0:
            for idx, annot in enumerate(annots):
                if annot.shape[0] > 0:
                    annot_padded[idx, :annot.shape[0], :] = annot
    else:
        annot_padded = torch.ones((len(annots), 1, 5)) * -1

    imgs = imgs.permute(0, 3, 1, 2)

    return {'img': imgs, 'annot': annot_padded, 'scale': scales}


class Resizer(object):
    """Convert ndarrays in sample to Tensors."""

    def __call__(self, sample, common_size=512):
        image, annots = sample['img'], sample['annot']
        height, width, _ = image.shape
        if height > width:
            scale = common_size / height
            resized_height = common_size
            resized_width = int(width * scale)
        else:
            scale = common_size / width
            resized_height = int(height * scale)
            resized_width = common_size

        image = cv2.resize(image, (resized_width, resized_height))

        new_image = np.zeros((common_size, common_size, 3))
        new_image[0:resized_height, 0:resized_width] = image

        annots[:, :4] *= scale

        return {'img': torch.from_numpy(new_image), 'annot': torch.from_numpy(annots), 'scale': scale}


class Augmenter(object):
    """Convert ndarrays in sample to Tensors."""

    def __call__(self, sample, flip_x=0.5):
        if np.random.rand() < flip_x:
            image, annots = sample['img'], sample['annot']
            image = image[:, ::-1, :]

            rows, cols, channels = image.shape

            x1 = annots[:, 0].copy()
            x2 = annots[:, 2].copy()

            x_tmp = x1.copy()

            annots[:, 0] = cols - x2
            annots[:, 2] = cols - x_tmp

            sample = {'img': image, 'annot': annots}

        return sample


class Normalizer(object):

    def __init__(self):
        self.mean = np.array([[[0.485, 0.456, 0.406]]])
        self.std = np.array([[[0.229, 0.224, 0.225]]])

    def __call__(self, sample):
        image, annots = sample['img'], sample['annot']

        return {'img': ((image.astype(np.float32) - self.mean) / self.std), 'annot': annots}
