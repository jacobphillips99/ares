from tqdm import tqdm

from ares.configs.open_x_embodiment_configs import (
    OpenXEmbodimentEpisode,
    OpenXEmbodimentEpisodeMetadata,
    get_dataset_information,
)
from ares.models.extractor import RandomInformationExtractor, VLMInformationExtractor
from ares.models.shortcuts import get_gemini_2_flash, get_gemini_15_flash
from main import build_dataset

dataset_filename = "jaco_play"
data_dir = "/workspaces/ares/data/oxe/"
builder, dataset_dict = build_dataset(dataset_filename, data_dir)
# extractor = VLMInformationExtractor(get_gemini_2_flash())
extractor = VLMInformationExtractor(get_gemini_15_flash())
ds = dataset_dict["train"]
print(f"working on 'train' out of {list(dataset_dict.keys())}")
dataset_info = get_dataset_information(dataset_filename)

print(len(ds))

# random_extractor = RandomInformationExtractor()
#
# for i, ep in tqdm(enumerate(ds)):
#     episode = OpenXEmbodimentEpisode(**ep)
#     if episode.episode_metadata is None:
#         # construct our own metadata
#         episode.episode_metadata = OpenXEmbodimentEpisodeMetadata(
#             file_path=f"episode_{i}.npy",  # to mock extension
#         )
import pickle

episode = pickle.load(open("episode.pkl", "rb"))
rollout = extractor.extract(
    episode, dataset_info, vlm_kwargs={"prompt_filename": "test_prompt.jinja2"}
)
breakpoint()
# breakpoint()
# # print(rollout)
# pickle.dump(episode, open("episode.pkl", "wb"))
