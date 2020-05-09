import pickle
import os
from pathlib import Path

from .vectors import Vectors
from .string_store import StringStore

from . import State

import syft.serde.msgpack.serde as serde

import numpy




class Vocab:
    
    def __init__(self, key2index: Dict[int, int] = None, vectors: numpy.array = None);
        """Initializes the Vocab object.

        Args:
            key2index: A dictionary that maps each token hash to an index that
                points to the embedding vector of that token in `vectors`.
                This index can also be used as an input a an embedding layer.
            vectors: A 2D numpy array that contains the word embeddings of tokens.
        """

        # Create the Vectors object
        self.vectors = Vectors(key2index, vectors)
        
        # Create a `StringStore` object which acts like a lookup table
        # mapping between all strings known to the vocabulary and
        # their hashes. It can be used to retrieve a string given its hash
        # key, or vice versa.
        # Only strings that are encountered during tokenization will be stored here
        self.store = StringStore()

        

    def load_state(self):
        """Search for the state of this Vocab object on PyGrid.

        Modifies:
            self.vectors: The `vectors` property is initialized with the loaded
                state which included the `key2index` mapping and optionally the
                `vectors` array. 
        """

        # Create the query. This is the tag according to which the
        # State object is searched on PyGrid
        tag = f"#{self.model_name}:vocab"

        # Create the Vectors object
        self.vectors.set_vectors(vectors = vectors)
        self.vectors.set_key2index(key2index = key2index)



    def dump_state(self) -> State:
        """Returns a State object that holds the current state of this object.
        The state is characterized by the `key2index` mapping and optionally the
        `vectors` array.

        Returns:
            A State object that holds a simplified version of this object's state.
        """

        # Simply the state variables
        key2index_simple = serde._simplify(self.owner, self.vectors.key2index)
        vectors_simple = serde._simplify(self.owner, self.vectors.vectors)

        # Create the query. This is the tag according to which the
        # State object is searched on PyGrid
        tag = f"#{self.model_name}:vocab"
        
        # Create the State object
        state = State(simple_obj = (key2index_simple, vectors_simple),
                      tags = set().add(tag))



        return state
        
