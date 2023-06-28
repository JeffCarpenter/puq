import os
import logging
import argparse
from tqdm import tqdm

import torch
from torchvision.transforms import transforms as T

from core import EPUQUncertaintyRegion, DAPUQUncertaintyRegion, RDAPUQUncertaintyRegion
from data.data import DiffusionSamplesDataset, GroundTruthsDataset
from utils import misc


def get_arguments():
    parser = argparse.ArgumentParser(description='Official implementation of "Principal Uncertainty Quantification with Spatial Correlation for Image Restoration Problems" paper. link: https://arxiv.org/abs/2305.10124')

    parser.add_argument('--method', type=str, required=True, help='Method to use: e_puq, da_puq or rda_puq.')
    parser.add_argument('--data', type=str, required=True, help='Data folder path.')
    parser.add_argument('--patch-res', type=int, default=None, help='Patch resolution to use: None to use the full image or int to use patches with 3xpxp dimensions where p is the chosen number.')

    parser.add_argument('--test-ratio', type=float, default=0.2, help='Test instances ratio out of the data folder.')
    parser.add_argument('--seed', type=int, default=42, help='Seed.')
    parser.add_argument('--gpu', type=int, default=None, help='GPU index to use, None for CPU.')
    parser.add_argument('--batch', type=int, default=4, help='Batch size to work on.')
    parser.add_argument('--num-workers', type=int, default=0, help='Number of workers for dataloaders.')

    # User-specified parameters for statistical guarantees
    parser.add_argument('--alpha', type=float, default=0.1, help='Coverage guarantee parameter.')
    parser.add_argument('--beta', type=float, default=0.1, help='Reconstruction guarantee parameter.')
    parser.add_argument('--q', type=float, default=0.9, help='Pixels ratio parameter for reconstruction guarantee.')
    parser.add_argument('--delta', type=float, default=0.1, help='Error level of guarantees.')

    # Technical parameters for calibration procedure
    parser.add_argument('--num-reconstruction-lambdas', type=int, default=100, help='Number of fine-grained lambdas parameters to be checked for reconstruction guarantee.')        # lambda1s
    parser.add_argument('--num-coverage-lambdas', type=int, default=100, help='Number of fine-grained lambdas parameters to be checked for coverage guarantee.')                    # lambda2s
    parser.add_argument('--num-pcs-lambdas', type=int, default=20, help='Number of fine-grained lambdas parameters to be checked for reducting the number of PCs at inference.')    # lambda3s
    parser.add_argument('--max-coverage-lambda', type=float, default=20.0, help='Maximal coverage lambda. (20.0 should be enougth for various tasks).')

    args = parser.parse_args()
    return args


def main(args):

    misc.setup_logging(os.path.join(os.getcwd(), 'log.txt'))
    logging.info(args)

    torch.manual_seed(args.seed)

    # DATA INIT

    cal_samples_dataset = DiffusionSamplesDataset(
        opt=args,
        calibration=True,
        transform=T.ToTensor()
    )

    cal_ground_truths_dataset = GroundTruthsDataset(
        opt=args,
        samples_dataset=cal_samples_dataset,
        transform=T.ToTensor()
    )

    test_samples_dataset = DiffusionSamplesDataset(
        opt=args,
        calibration=False,
        transform=T.ToTensor()
    )

    # PUQ INIT

    if args.method == 'e_puq':
        puq = EPUQUncertaintyRegion(args)
    elif args.method == 'da_puq':
        puq = DAPUQUncertaintyRegion(args)
    elif args.method == 'rda_puq':
        puq = RDAPUQUncertaintyRegion(args)
    else:
        message = 'Unrecognized method name.'
        logging.error(message)
        raise Exception(message)

    # CALIBRATION

    puq.calibration(cal_samples_dataset, cal_ground_truths_dataset)

    # INFERENCE

    K = test_samples_dataset.num_samples_per_image

    samples_dataloader = torch.utils.data.DataLoader(
        test_samples_dataset,
        batch_size=K,
        num_workers=args.num_workers,
        shuffle=False,
        collate_fn=None if args.patch_res is None else misc.concat_patches
    )

    logging.info('Applying inference...')
    for samples in tqdm(samples_dataloader):
        samples = samples.view(samples.shape[0]//K, K, -1)
        samples = samples[:, :puq.max_pcs]

        # TODO: Implemetation for metrics evaluations
        uncertainty_region = puq.inference(samples)

    logging.info('Done.')


if __name__ == "__main__":
    args = get_arguments()
    main(args)
