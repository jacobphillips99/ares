import os

ARES_DATA_DIR = "/workspaces/ares/data"
ARES_OXE_DIR = os.path.join(ARES_DATA_DIR, "oxe")
ARES_VIDEO_DIR = os.path.join(ARES_DATA_DIR, "videos")

# using oxe-downloader
# oxe-download --dataset "name" --path $ARES_OXE_DIR!!!
DATASET_NAMES = [
    {
        "dataset_filename": "ucsd_kitchen_dataset_converted_externally_to_rlds",
        "dataset_formalname": "UCSD Kitchen",
    },
    {
        "dataset_filename": "cmu_franka_exploration_dataset_converted_externally_to_rlds",
        "dataset_formalname": "CMU Franka Exploration",
    },
    {
        "dataset_filename": "berkeley_fanuc_manipulation",
        "dataset_formalname": "Berkeley Fanuc Manipulation",
    },
    {
        "dataset_filename": "cmu_stretch",
        "dataset_formalname": "CMU Stretch",
    },
    {"dataset_filename": "cmu_play_fusion", "dataset_formalname": "CMU Play Fusion"},
    {
        "dataset_filename": "jaco_play",
        "dataset_formalname": "USC Jaco Play",
    },
    {
        "dataset_filename": "dlr_edan_shared_control_converted_externally_to_rlds",
        "dataset_formalname": "DLR Wheelchair Shared Control",
    },
    {
        "dataset_filename": "imperialcollege_sawyer_wrist_cam",
        "dataset_formalname": "Imperial Wrist Cam",
    },
    {
        "dataset_filename": "tokyo_u_lsmo_converted_externally_to_rlds",
        "dataset_formalname": "LSMO Dataset",
    },
    {
        "dataset_filename": "nyu_rot_dataset_converted_externally_to_rlds",
        "dataset_formalname": "NYU ROT",
    },
    {
        "dataset_filename": "ucsd_pick_and_place_dataset_converted_externally_to_rlds",
        "dataset_formalname": "UCSD Pick Place",
    },
    {
        "dataset_filename": "asu_table_top_converted_externally_to_rlds",
        "dataset_formalname": "ASU TableTop Manipulation",
    },
    {
        "dataset_filename": "viola",
        "dataset_formalname": "Austin VIOLA",
    },
    {
        "dataset_filename": "kaist_nonprehensile_converted_externally_to_rlds",
        "dataset_formalname": "KAIST Nonprehensile Objects",
    },
    {
        "dataset_filename": "berkeley_mvp_converted_externally_to_rlds",
        "dataset_formalname": "Berkeley MVP Data",
    },
    # Saytap does not have pixel data
    # {
    #     "dataset_filename": "utokyo_saytap_converted_externally_to_rlds",
    #     "dataset_formalname": "Saytap",
    # },
]
