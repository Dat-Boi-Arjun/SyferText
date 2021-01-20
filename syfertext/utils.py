from syft.workers.base import BaseWorker

import numpy as np

import mmh3
import os
import re
from pathlib import Path
import dill

from typing import Pattern
from typing import Match
from typing import Tuple
from typing import Union
from typing import Dict


def hash_string(string: str) -> int:
    """Create a hash for a given string.
    Hashes created by this functions will be used everywhere by
    SyferText to represent tokens.
    """

    key = mmh3.hash64(string, signed=False, seed=1)[0]

    return key


def normalize_slice(length: int, start: int, stop: int, step: int = None):
    """This function is used to convert the negative slice boundaries to positive values.
    eg. start = -4, stop = -1, length = 6 gets converted to start = 2, stop = 5

    Args:
        length (int): the length of the document to slice
        start (int): the start index of the slice
        stop (int): the stop index of the slice
        step (int): the step value for the slice

    Returns:
        (start, stop) : pair of non-negative integer values signifying the
            normalized values of the slice
    """
    assert step is None or step == 1, "Stepped slices with steps greater than one are not supported"

    # if start is none, that means we need to start from 0 index
    if start is None:
        start = 0

    # if start is negative, we add the length to get its actual index
    elif start < 0:
        start += length

    # start should not exceed the length of the document
    # also max(0,start) ensures the start is never negative
    start = min(length, max(0, start))

    # stop is None, that means we need stop to be the last index+1
    if stop is None:
        stop = length

    # add the length to get the actual positive index for stop if
    # is negative
    elif stop < 0:
        stop += length

    # stop should be less than or equal to length. Also max(start,stop) ensures that start <= stop
    stop = min(length, max(start, stop))

    return start, stop


# The following three functions for compiling prefix, suffix and infix regex are adapted
# from Spacy  https://github.com/explosion/spaCy/blob/master/spacy/util.py.
def compile_prefix_regex(entries: Tuple) -> Pattern:
    """Compile a sequence of prefix rules into a regex object.

    Args:
        entries (tuple): The prefix rules, e.g. syfertext.punctuation.TOKENIZER_PREFIXES.

    Returns:
        The regex object. to be used for Tokenizer.prefix_search.
    """

    if "(" in entries:
        # Handle deprecated data
        expression = "|".join(["^" + re.escape(piece) for piece in entries if piece.strip()])
        return re.compile(expression)
    else:
        expression = "|".join(["^" + piece for piece in entries if piece.strip()])
        return re.compile(expression)


def compile_suffix_regex(entries: Tuple) -> Pattern:
    """Compile a sequence of suffix rules into a regex object.

    Args:
        entries (tuple): The suffix rules, e.g. syfertext.punctuation.TOKENIZER_SUFFIXES.

    Returns:
        The regex object. to be used for Tokenizer.suffix_search.
    """

    expression = "|".join([piece + "$" for piece in entries if piece.strip()])

    return re.compile(expression)


def compile_infix_regex(entries: Tuple) -> Pattern:
    """Compile a sequence of infix rules into a regex object.

    Args:
        entries (tuple): The infix rules, e.g. syfertext.punctuation.TOKENIZER_INFIXES.

    Returns:
        The regex object. to be used for Tokenizer.infix_finditer.
    """

    expression = "|".join([piece for piece in entries if piece.strip()])

    return re.compile(expression)


def create_state_query(pipeline_name: str, state_name: str) -> str:
    """Construct an ID that will be used to search for a State object
    on PyGrid.

    Args:
        pipeline_name: The name of the pipeline to which the State
            object belongs.
        state_name: The name of the State object.

    Returns:
        A `str` representing the ID of the State object that is used as
            a search query.
    """

    query = f"{pipeline_name}:{state_name}"

    return query


def search_resource(
    query: str, local_worker: BaseWorker
) -> Union["State", "StatePointer", "Pipeline", "PipelinePointer", None]:
    """Searches for a resource (State or Pipeline object) on PyGrid.
    It first checks out whether the object could be found on the local worker.
    Then it checks the local storage whether the resource has been cached or not.
    Else, search is triggered across all workers known to the
    local worker.

    Args:
        query: The ID of the object to be searched for.
        local_worker: The local worker on which the state should
            be first searched
    Returns:
        An object whose ID is specified by `query` if the object is found
        on the local worker. Or, a pointer to it if the object is on a remote
        worker. If no object is found, None is returned.
    """

    # Start first by searching for the resource on the local worker.
    result = local_worker.search(query=query)

    # If an object is found, then return it.
    if result:

        # Make sure only one resource object is found
        assert (
            len(result) == 1
        ), f"Ambiguous result: multiple objects matching the search query were found on worker `{local_worker}`."

        return result[0]

    # Now look into the local storage for states
    data_path = os.path.join(str(Path.home()), "SyferText", "cache")

    # Since : is a reserved character for naming files, replacing with - instead in file_name
    tokens = query.split(":")
    file_name = query.replace(":", "-")

    # tokens[0] is the name of the pipeline directory
    data_path = os.path.join(data_path, tokens[0])

    if os.path.exists(data_path):
        # target contains the name of the file
        target = str("/{}.pkl".format(file_name))

        if os.path.isfile(data_path + target) and os.path.getsize(data_path + target) > 0:
            # Make file object
            state_cache = open(data_path + target, "rb")

            # Load into simplified pipeline object and return
            simplified_state = dill.load(state_cache)

            return simplified_state

    # If no object is found on the local worker, search on all
    # workers connected to the local_worker
    for _, location in local_worker._known_workers.items():

        # Search for the object on this worker. (The result is a list)
        result = local_worker.request_search(query=query, location=location)

        # If an object is found, process the result.
        if result:

            # Make sure only one object is found
            assert (
                len(result) == 1
            ), f"Ambiguous result: multiple objects matching the search query were found on worker `{location}`."

            # Get the pointer object returned
            object_ptr = result[0]

            return object_ptr


class MsgpackCodeGenerator:
    def __init__(self):
        pass

    def __call__(self, class_name: str) -> int:
        """Generates and returns a unique msgpack code.

        Args:
            class_name: The name of class for which the msgpack code is required.

        Returns:
            An integer to serve as a msgpack serialization code.
        """

        # the code Msgpack is generated as the hash of class name
        return hash_string(class_name)


msgpack_code_generator = MsgpackCodeGenerator()


def create_mpc_config(worker: BaseWorker) -> Dict[str, object]:
    """Create basic configurations for performing SMPC. This includes
    choosing the workers that will hold the shares and the crypto provider.

    Args:
        worker: The worker on which encryption is performed.

    returns:
        a dictionary that holds configuration for performing SMPC encryption.
        Here is an example
        - config['node_0'] for the first node to hold
          the shares.
        - config['node_1'] for the second node to hold
          the shares.
        - config['crypto_provider'] for the node that
          provides crypto primitives.
        - etc


    TODO:
        The workers' choice is currently done at random.
            It should be done in a more informed way in future versions
            depending on the use cases we encounter.
    """

    # Get a dictionary containing all known workers except 'me', the
    # local workers. It seems that using 'me' is causing problems in
    # SMPC mode.
    known_workers = {
        worker_id: worker
        for worker_id, worker in worker._known_workers.items()
        if worker_id != "me"
    }

    # If only one worker (the owner) is present on the network. No config
    # is created
    if len(known_workers) == 1:
        return None

    # Initialize the configuration dict as an empy dictionary
    mpc_config = {}

    # If only two nodes are available, choose them to hold shares.
    if len(known_workers) == 2:
        for i, node_id in enumerate(known_workers):
            mpc_config[f"node_{i}"] = known_workers[node_id]

        # Set the crypto provider
        mpc_config["node_2"] = mpc_config["node_1"]

    # Randomly chose three different workers:
    # two for holding the shares
    # and one as a crypto provider.
    if len(known_workers) >= 3:

        # Randomly choose nodes without replacement
        selected_node_ids = np.random.choice(a=list(known_workers.keys()), size=3, replace=False)

        # Use the nodes in the config
        for i, node_id in enumerate(selected_node_ids):
            mpc_config[f"node_{i}"] = known_workers[node_id]

    return mpc_config
