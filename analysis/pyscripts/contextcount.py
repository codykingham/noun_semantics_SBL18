'''
This module contains a second generation of a
context-selection class, originally developed in 
my master's thesis, the results of which can be
perused in the following repo:
https://github.com/codykingham/verb_semantics
The class was originally called an Experiment class. 

The primary problems the ContextCount class solves
is how to 1. select target words and co-occurring words
according to desired contexts, each with unique and complex
parameters, and 2. how to tokenize each resulting context
into a string that can then be counted. Previous versions
of this class attempted to access the ETCBC syntax data
through a series of loops with Text-Fabric node iterations
and feature calls. But as one multiplies the potential
linguistic contexts a given form can occur in, one must 
also multiply the complexity of the code, adding a confusing
array of if/else checks that build into a tangled nest of code.
Then each of the results must somehow be delivered, like a synchronized 
dance, to the precise tokenizer function that knows what the 
specific context looks like. This approach was cumbersome,
illegible, and frought with opportunities for accidents.

ContextCount applies a rather simple approach that was made
possible by Text-Fabric's implementation of powerful search
templates (by Dirk Roorda). Each template is simply a Python
string that plainly describes the linguistic context without
bureaucratic overhead. For instance, to find a Subject function
phrase within a verbal clause requires only the following string:

clause kind=VC
    phrase function=Subj

The search function then delivers this search into the form
of a simple tuple of result nodes, in this case a list of 2-tuples.

With a search template in hand that delivers ordered results, the
ContextCount class then only requires instructions on how to 
tokenize the results. This is done by linking each search template
to a simple Python tokenizer function. The tokenizer takes arguments
that tell it the target and co-occurring words' index number within 
the search template.

This method has many advantages over the first-gen, code-based 
format. With the old format, I gained extensibility
at the expense of readability and clarity. In the new method,
I maintain extensibility while maximizing clarity. This includes:

√ selection parameters for bases and targets clearly described: 
    templates are very easy to read/edit compared with code.
√ individual clause elements chosen separately but can be 
    united in a dictionary keyed by the clause; 
    good for both frame spaces and individual feature spaces
√ all parameters coordinated at once in one readable space (template)
    to avoid having to reclarify multiple parameters in multiple
    places

The search templates are delivered to ContextCount in the form of 
a dictionary of keys mapped to search templates, tokenizer functions, 
and other optional procedures. In this repository, the context-selection
parameters will be stored in a separate file, contextparameters.py.

After the search templates are run and the contexts tokenized,
ContextCount counts the strings into a dictionary which is then
returned as a Pandas co-occurrence matrix. The matrix is 
TARGET x CO-OCCURRENCES

The ContextCount class also has a set of helper attributes
that map any given co-occurring element in the counts back to 
its individual examples. 
'''

import collections
import numpy as np
import pandas as pd

class ContextCount:
    
    def __init__(self, parameters_dict, tf=None, min_observation=10, frame=False):
        '''
        parameters_dict is a dictionary with the following keys and values:
        
        template - a TF search template (string)
        target - the index of the target word
        bases - tuple of basis indexes
        target_tokenizer - a function to construct target tokens, requires index of target
        basis_tokenizer - a function to construct basis tokens, requires index of basis
        *kwargs - optional dict of keyword arguments for formatting the template (if any)
        *sets - optional dict containing sets arguments for TF.search
        *collapse_instances - optional boolean on whether to collapse multiple instances of a 
                              basis element at the result level; default is False
        
        There are two additional class parameters:
        
        tf - an instance of Text-Fabric
        min_observation - a minimum number of observations that are required for a target word
        frame - tells class whether to weave results from multiple searches into a single frame,
                organized by clause node
        
        A set of helper attributes with mappings from the tokens to the individual 
        search results are included under:
        
        ContextCount.target2gloss
        ContextCount.target2lex
        ContextCount.target2node
        ContextCount.clause2basis2result
        ContextCount.target2basis2result
        '''
        
        self.min_obs = min_observation # minimum observation requirement
        
        # Text-Fabric method short forms
        F, E, T, L, S = tf.F, tf.E, tf.T, tf.L, tf.S
        self.tf_api = tf
        
        # raw experiment_data[target_token][clause][list_of_bases_tokens]
        experiment_data = collections.defaultdict(lambda: collections.defaultdict(list)) if not frame else\
                          collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(list)))
        self.collapse_instances = False # count presence/absence of features in a clause, i.e. don't add up multiple instances
        count_experiment = self.inventory_count if not frame else self.frame_count
        
        # helper data, for mappings between bases and TF data
        self.target2gloss = dict()
        self.target2lex = dict()
        self.target2node = dict()
        self.clause2basis2result = collections.defaultdict(lambda: collections.defaultdict(list))

        # run the search templates and tokenize results
        for param in parameters:            
            search_tmpl = param['template']
            target_i = param['target']
            bases_i = param['bases']
            target_tokener = param['target_tokenizer']
            basis_tokener = param['basis_tokenizer']
            tmpl_kwargs = param.get('kwargs', None)
            tmpl_sets = param.get('sets', None)
            self.collapse_instances = param.get('collapse_instances', False)
            
            # run search query on template
            search_tmpl = search_tmpl if not tmpl_kwargs else search_tmpl.format(**tmpl_kwargs)    
            search = sorted(S.search(search_templ, sets=tmpl_sets))

            # make target token
            for specimen in search:
                
                # get clause for clause-token mapping
                clause = specimen[0] if F.otype.v(specimen[0]) == 'clause'\
                             else next(r for r in specimen if F.otype.v(r) == 'clause')
                target = specimen[target_i]
                target_token = target_tokener(target)

                # make bases tokens, map to clause
                for basis_i in bases_i:
                    basis = specimen[basis_i]
                    basis_token = basis_tokener(basis, target)
                    basis_tokens = (basis_token,) if type(basis_token) == str else basis_token
                    if not frame:
                        experiment_data[target_token][clause].extend(basis_tokens)
                    else:
                        basis_unit = L.u(basis, 'phrase') if F.otype.v(basis) == 'word' else basis
                        experiment_data[target_token][clause][basis_unit].extend(basis_tokens)
                    
                    # add helper data 1, basis to results mapping
                    for bt in basis_tokens:
                        self.clause2basis2result[clause][bt].append(specimen)

                # add helper data 2, maps from targets to glosses, lexemes, and nodes
                self.target2gloss[target_token] = F.gloss.v(L.u(target, 'lex')[0])
                self.target2lex[target_token] = L.u(target, 'lex')[0]
                self.target2node[target_token] = target
                
        # finalize data
        count_experiment(experiment_data)
    
    
    def inventory_count(self, experiment_data):
        '''
        Counts experiment data into a dataframe from an
        experiment data dictionary structured as:
        experiment_data[target_token][clause][list_of_bases_tokens]
        
        --input--
        dict
        
        --output--
        pandas df
        '''
        
        ecounts = collections.defaultdict(lambda: collections.Counter())
        
        for target, clauses in experiment_data.items():
            for clause, bases in clauses.items():
                bases = bases if not self.collapse_instances else set(bases)
                bases = bases if not set(bases) == {'ø'} else {'ø'} # count only one null value
                ecounts[target].update(bases)
                
        counts = dict((target, counts) for target, counts in ecounts.items()
                                if sum(counts.values()) >= self.min_obs)
        
        self.data = pd.DataFrame(counts).fillna(0)
        self.raw_data = experiment_data
        
        # assemble helper data: mapping from basis to list of search results
        self.basis2result = collections.defaultdict(list)
        for clause, bases in self.clause2basis2result.items():
            for basis, results in bases.items():
                self.basis2result[basis].extend(results)
        self.target2basis2result = collections.defaultdict(lambda: collections.defaultdict(list))
        for target, clauses in experiment_data.items():
            for clause, bases in clauses.items():
                for basis, results in self.clause2basis2result[clause].items():
                    self.target2basis2result[target][basis].extend(results)
        
    
    def frame_count(self, experiment_data):
        '''
        Counts frame experiment data into a dataframe from an
        experiment data dictionary structured as:
        experiment_data[target_token][clause][list_of_bases_tokens]
        
        Rather than counting individual instances of bases in a result,
        the frame_count sorts and assembles all the basis elements into
        a single string (i.e. "frame") which is then counted.
        
        --input--
        dict
        
        --output--
        pandas df
        '''
        
        ecounts = collections.defaultdict(lambda: collections.Counter())
        
        # helper data
        self.basis2result = collections.defaultdict(list)
        self.target2basis2result = collections.defaultdict(lambda: collections.defaultdict(list))
        
        for target, clauses in experiment_data.items():
            for clause, phrases in clauses.items():
                
                bases = tuple(tuple(bs) for bs in phrases.values())
                bases = bases if not set(bases) == {('ø',)} else (('ø',),)        
                
                # recursively combine all possible frame elements
                for frame_list in self.stitch_frames(bases):
                    frame = '|'.join(sorted(frame_list))
                    ecounts[target][frame] += 1
                
                    # helper data; combine all search results into a single result mapped to the frame
                    frame_results = set()
                    for basis, results in self.clause2basis2result[clause].items():
                        if basis not in frame_list:
                            continue
                        for result in results:
                            frame_results |= set(result)
                    self.basis2result[frame].append(tuple(frame_results))
                    self.target2basis2result[target][frame].append(tuple(frame_results))
                
        counts = dict((target, counts) for target, counts in ecounts.items()
                                if sum(counts.values()) >= self.min_obs)
        
        self.data = pd.DataFrame(counts).fillna(0)
        self.raw_data = experiment_data
        
        
    def stitch_frames(self, tokenlists):
        '''
        A recursive constructor for frames
        with multiple head elements.
        Returns all possible frames given
        the presence of multiple heads per
        phrase. Requires a list of token lists,
        where each token list corresponds to a phrase
        with multiple heads that have been tokenized.

        Credit: Thanks to Dirk Roorda for
        this code and helping me understand
        how it works.
        '''
        if len(tokenlists) == 1:
            for token in tokenlists[0]:
                yield (token,)

        elif len(tokenlists) > 1:
            for result in self.stitch_frames(tokenlists[1:]):
                for token in tokenlists[0]:
                    yield (token, *result)
