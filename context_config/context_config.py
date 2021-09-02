from abc import ABC, abstractmethod
from intervaltree import IntervalTree, Interval
from collections.abc import Mapping, MutableMapping, Iterable

class BaseConfig(ABC):
    def __init__(self, parent=None):
        self.parent = parent
    
    @abstractmethod
    def lookup(self, key):
        pass
    
    @abstractmethod
    def configure(self, key, value):
        pass
    
    @abstractmethod
    def _keys(self):
        pass
    
    def __getitem__(self, key):
        if isinstance(key, tuple):
            if len(key)==1:
                return self.lookup(key[0])
            elif len(key)==2:
                return self.lookup(key[0])[key[1]]
            else:
                return self.lookup(key[0])[key[1:]]
        return self.lookup(key)

    def __setitem__(self, key, value):
        if isinstance(key, tuple):
            if key[0] in self.keys():
                if len(key)==1:
                    return self.configure(key[0], value)
                elif len(key)==2:
                    self.lookup(key[0])[key[1]] = value
                    return
                else:
                    self.lookup(key[0])[key[1:]] = value
                    return
            elif self.parent is not None:
                self.parent[key] = value
                return
            else:
                raise KeyError(f"{key} has not been defined in this context.") 
        self.configure(key, value)

    def __getattr__(self, key):
        return self.__getitem__(key)
    
    def subcontext(self, **attrs):
        return self.__class__(self, **attrs)
    
    def keys(self):
        keys = set(self._keys())
        if self.parent is not None:
            keys.update(self.parent.keys())
        return list(keys)
    def items(self):
        return [(k,self.lookup(k)) for k in self.keys()]
    
    def __dir__(self):
        return super().__dir__() + self.keys() 
    
    def __contains__(self, key):
        return key in self.keys()
    
class DictConfig(BaseConfig):
    def __init__(self, parent=None, attrs=None, **kwargs):
        super().__init__(parent=parent, **kwargs)
        if attrs is None:
            attrs = {}
        self._attrs = dict(attrs)
    
    def lookup(self, key):
        if key in self._attrs:
            return self._attrs[key]
        if self.parent is not None:
            return self.parent.lookup(key)
        raise KeyError(f"{key} has not been defined in this context.")
    
    def configure(self, key, value):
        self._attrs[key] = value
    
    def _keys(self):
        return self._attrs.keys()
    
    
class IntervalConfig(BaseConfig):
    _tree: IntervalTree
    

    @classmethod
    def from_label_dict(cls, d):
        ivs = [Interval(*map(int, k.split("-")), v) for k,v in d.items()]
        return cls(IntervalTree(ivs))
    
    def add_group(self, name, group):
        self[name] = group

    def key_to_label(self, key):
        return f"{key[0]}-{key[1]}"

    def label_to_key(self, label):
        return tuple(map(int, label.split("-")))

    def to_label_dict(self):
        return {f"{iv.begin}-{iv.end}": iv.data for iv in sorted(self._tree)}
        
    def to_dict(self):
        return {(iv.begin,iv.end): iv.data for iv in sorted(self._tree)}
    
    def __init__(self, parent=None, tree=None, **kwargs):
        super().__init__(parent=parent)
        if tree is None:
            tree = IntervalTree()
        if not isinstance(tree, IntervalTree):
            raise TypeError("tree must be an instance of IntervalTree.")
        self._tree = tree
        
    def lookup(self, key):
        if isinstance(key, str):
            key = self.label_to_key(key)
        if isinstance(key, int):
            return self.value(key)
        elif isinstance(key, tuple) and len(key)==2:
            return self.overlap_content(*key)
        elif isinstance(key, Iterable):
            return self.values_at(key)
        elif isinstance(key, slice):
            start = key.start or self.start
            stop = key.stop or self.end
            if key.step is None:
                return self.overlap(start, stop)
            else:
                return self.values_at(range(start, stop, key.step))
    @property
    def start(self):
        return self._tree.begin()

    @property
    def end(self):
        return self._tree.end()

    def configure(self, key, value):
        if isinstance(key, str):
            key = self.label_to_key(key)
        if isinstance(key, slice):
            start, stop, step = key.start, key.stop, key.step
        elif isinstance(key, tuple):
            if len(key)==2:
                start, stop = key
                step = None
            elif len(key)==3:
                start, stop, step = key
            else:
                raise ValueError("Setting intervals with tuple must be  \
                            of form (start, end) or (start, end, step)")
        else:
            raise TypeError("Wrong type. Setting intervals can only be done using a \
                            slice or tuple of (start, end) or (start, end, step)")
        if start is None:
            start = self.start
        if stop is None:
            stop = self.end
        if step is None:
            self.set_interval(start, stop, value)
        else:
            indices = list(range(start,stop,step))
            for begin,end,val in zip(indices[:-1], indices[1:], value):
                 self.set_interval(begin, end, val)
    
    def delete(self, key):
        if isinstance(key, str):
            key = self.label_to_key(key)
        elif isinstance(key, tuple) and len(key)==2:
            self._tree.chop(*key)
        elif isinstance(key, slice):
            self._tree.chop(key.start, key.end)
        else:
            raise TypeError("Must pass a tuple of (begin,end) or slice.")
    
    def _keys(self):
        for iv in sorted(self._tree):
            yield iv.begin, iv.end

    def labels(self):
        return map(self.key_to_label, self.keys())

    def items(self):
        for iv in sorted(self._tree):
            yield (iv.begin,iv.end), iv.data

    def values(self):
        for iv in sorted(self._tree):
            yield iv.data

    def __iter__(self):
        return self.keys()

    def __len__(self):
        return len(self._tree)

    def __bool__(self):
        return bool(len(self._tree))

    def __contains__(self, key):
        return bool(self[key])

    def __getstate__(self):
        return tuple(sorted([tuple(iv) for iv in self._tree]))

    def __setstate__(self, d):
        ivs = [Interval(*iv) for iv in d]
        self._tree = IntervalTree(ivs)

    def overlap(self, begin, end):
        hits = sorted(self._tree.overlap(begin, end))
        return [Interval(max(iv.begin, begin), min(iv.end, end), iv.data)
                    for iv in hits]

    def overlap_content(self, begin, end):
        hits = sorted(self._tree.overlap(begin, end))
        if len(hits)==1:
            return hits[0].data
        return [hit.data for hit in hits]

    def value(self, index):
        hits = sorted(self._tree.at(index))
        if hits:
            return hits[0].data
        raise KeyError(f"No value found at {index}")
        
    def values_at(self, indices):
        return [self.value(i) for i in indices]

    def set_interval(self, begin, end, value):
        self._tree.chop(begin, end)
        self._tree.addi(begin, end, value)
