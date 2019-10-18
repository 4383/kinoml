from string import ascii_letters
import re
import logging
import requests
from collections import Counter


logger = logging.getLogger(__name__)


class Biosequence(str):
    """
    Base class for string representations of biological polymers
    (nucleic acids, peptides, proteins...)

    TODO: How to handle several mutations at the same time, while
          keeping indices relevant (after a deletion, a replacement
          or insertion position might be wrong).
    """

    ALPHABET = set(ascii_letters)
    _ACCESSION_URL = None
    ACCESSION_MAX_RETRIEVAL = 50

    def __new__(cls, value, header='', *args, **kwargs):
        if not all(c in cls.ALPHABET for c in value):
            raise ValueError(f'Biosequence can only contain characters in {cls.ALPHABET}')
        s = super().__new__(cls, value, *args, **kwargs)
        s.header = header
        return s

    @classmethod
    def from_accession(cls, *accession):
        """
        Get FASTA sequence from an online accession identifier

        Parameters
        ----------
        accession : str
            NCBI identifier. Multiple can be provided!

        Returns
        -------
        Biosequence or list of Biosequencs
        """
        if cls._ACCESSION_URL is None:
            raise NotImplementedError
        if len(accession) > cls.ACCESSION_MAX_RETRIEVAL:
            raise ValueError(f"You can only provide {cls.ACCESSION_MAX_RETRIEVAL} accessions at the same time.")
        r = requests.get(cls._ACCESSION_URL.format(','.join(accession)))
        r.raise_for_status()
        sequences = []
        for line in r.text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith('>'):
                sequences.append({'header': line[1:], 'sequence': []})
            else:
                sequences[-1]['sequence'].append(line)
        if not sequences:
            return
        objects = [cls(''.join(s['sequence']), header=s['header']) for s in sequences]
        if not objects:
            return
        if len(objects) == 1:
            return objects[0]
        return objects


    def cut(self, start, stop, check=True):
        """
        Slice a sequence using biological notation

        Parameters
        ----------
        start : str
            Starting element and 1-indexed position; e.g. C123
        end : str
            Ending element and 1-indexed position; e.g. T234
            This will be included in the resulting sequence
        check : bool, optional=True
            Whether to test if the existing elements correspond to those
            specified in the bounds

        Returns
        -------
        Biosequence
            Substring corresponding to [start, end]. Right bound is included!

        Examples
        --------
        >>> s = Biosequence("ATCGTHCTCH")
        >>> s.cut("T2", "T8")
            "TCGTHCT"
        """
        start_res, start_pos = start[0], int(start[1:])
        stop_res, stop_pos = stop[0], int(stop[1:])
        if check:
            assert start_res == self[start_pos-1], f"Element at position {start_pos} is not {start_res}"
            assert stop_res == self[stop_pos-1], f"Element at position {stop_pos} is not {stop_res}"
        return self.__class__(self[start_pos-1:stop_pos], header=f"{self.header}{ ' | ' if self.header else '' }Cut: {start}/{stop}")

    def mutate(self, *mutations, raise_errors=True):
        """
        Apply a mutation on the sequence using biological notation.

        Parameters
        ----------
        mutations : str
            Mutations to be applied. Indices are always 1-indexed. It can be one of:
            - substitution, like ``C234T`` (C at position 234 will be replaced by T)
            - deletion, like ``L746-A750del`` (delete everything between L at position 746
              A at position 750, bounds not included)
            - insertion, like ``1151Tins`` (insert a T after position 1151)
        raise_errors : bool, optional=True
            Raise ValueError if one of the mutations is not supported.
        Returns
        -------
        Biosequence
            The edited sequence

        Examples
        --------
        >>> s = Biosequence("ATCGTHCTCH")
        >>> s.mutate("C3P")
            "ATPGTHCTCH"
        >>> s.mutate("T2-T5del")
            "ATTHCTCH"
        >>> s.mutate("5Tins")
            "ATCGTTHCTCH"
        """
        # We can only handle one insertion or deletion at once now
        mutation_types = {m: self._type_mutation(m, raise_errors) for m in mutations}
        mutation_count = Counter(mutation_types.values())
        if mutation_count['insertion'] + mutation_count['deletion'] > 1:
            msg = f"Only one simultaneous insertion or deletion is currently supported. You provided `{','.join(mutations)}`"
            if raise_errors:
                raise ValueError(msg)
            logger.warning("Warning: %s", msg)
            return None

        # Reverse alphabetical order (substitutions will come first)
        mutated = self
        for mutation in sorted(mutations, key=lambda m: mutation_count[m], reverse=True):
            if None in (mutation, mutation_types[mutation]):
                continue
            operation = getattr(mutated, f"_mutate_with_{mutation_types[mutation]}")
            mutated = operation(mutation)
        mutated.header += f" (mutations: {', '.join(mutations)})"
        return mutated

    @staticmethod
    def _type_mutation(mutation, raise_errors=True):
        """
        Guess which kind of operation ``mutation`` is asking for.
        """
        if 'ins' in mutation:
            return 'insertion'
        if 'del' in mutation:
            return 'deletion'
        if re.search(r'([A-Z])(\d+)([A-Z])', mutation) is not None:
            return 'substitution'
        if raise_errors:
            raise ValueError(f'Mutation `{mutation}` is not recognized')

    def _mutate_with_substitution(self, mutation):
        """
        Given ``XYYYZ``, replace element ``X`` at position ``YYY`` with ``Z``.

        Parameters
        ----------
        mutation : str
            Replacement to apply. It must be formatted as
            ``[existing element][1-indexed position][new element]``

        Returns
        -------
        str
            Replaced sequence
        """
        # replacement: e.g. C1156Y
        search = re.search(r'([A-Z])(\d+)([A-Z])', mutation)
        if search is None:
            raise ValueError(f"Mutation `{mutation}` is not a valid substitution.")
        old, position, new = search.groups()
        assert new in self.ALPHABET, f"{new} is not a valid {self.__class__.__name__} character ({self.ALPHABET})"
        index = int(position) - 1
        return self.__class__(f"{self[:index]}{new}{self[index+1:]}")

    def _mutate_with_deletion(self, mutation):
        """
        Given ``AXXX-BYYYdel``, delete everything between elements ``A`` and ``B`` at positions
        ``XXX`` and ``YYY``, respectively. ``A`` and ``B`` will still be part of the resulting sequence.

        Parameters
        ----------
        mutation : str
            Replacement to apply. It must be formatted as
            ``[starting element][1-indexed starting position]-[ending element][1-indexed ending position]del``

        Returns
        -------
        str
            Edited sequence
        """
        # deletion: e.g. L746-A750del
        search = re.search(r'[A-Z](\d+)-[A-Z](\d+)del', mutation)
        if search is None:
            raise ValueError(f"Mutation `{mutation}` is not a valid deletion.")
        start = int(search.group(1))
        end = int(search.group(2)) - 1
        return self.__class__(f"{self[:start]}{self[end:]}")

    def _mutate_with_insertion(self, mutation):
        """
        Given ``XXXAdel``, insert element ``A`` at position ``XXX``.

        Parameters
        ----------
        mutation : str
            Insertion to apply. It must be formatted as
            ``[1-indexed insert position][element to be inserted]ins``

        Returns
        -------
        str
            Edited sequence
        """
        # insertion: e.g. 1151Tins
        search = re.search(r'(\d+)([A-Z]+)ins', mutation)
        if search is None:
            raise ValueError(f"Mutation `{mutation}` is not a valid insertion.")
        position = int(search.group(1))
        residue = search.group(2)
        assert all(r in self.ALPHABET for r in residue)
        return self.__class__(f"{self[:position]}{residue}{self[position:]}")


class AminoAcidSequence(Biosequence):
    ALPHABET = "ACDEFGHIKLMNPQRSTVWY"
    _ACCESSION_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=protein&id={}&rettype=fasta&retmode=text"


class DNASequence(Biosequence):
    ALPHABET = "ATCG"
    _ACCESSION_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&id={}&rettype=fasta&retmode=text"


class RNASequence(Biosequence):
    ALPHABET = "AUCG"
    _ACCESSION_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&id={}&rettype=fasta&retmode=text"

