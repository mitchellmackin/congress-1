#! /usr/bin/python

import logging
import compile
import uuid

# A unifier designed for the bi_unify_atoms routine
# which is used by a backward-chaining style datalog implementation.
# Main goal: minimize memory allocation by manipulating only unifiers
#   to keep variable namespaces separate.

class BiUnifier(object):
    """ A unifier designed for bi_unify_atoms.  Recursive
        datastructure.  When adding a binding variable u to
        variable v, keeps a reference to the unifier for v.
        A variable's identity is its name plus its unification context.
        This enables a variable with the same name but from two
        different atoms to be treated as different variables. """
    class Value(object):
        def __init__(self, value, unifier):
            # actual value
            self.value = value
            # unifier context
            self.unifier = unifier

        def __str__(self):
            return "<{},{}>".format(
                str(self.value), repr(self.unifier))

        def recur_str(self):
            if self.unifier is None:
                recur = str(self.unifier)
            else:
                recur = self.unifier.recur_str()
            return "<{},{}>".format(
                str(self.value), recur)

        def __eq__(self, other):
            return self.value == other.value and self.unifer == other.unifier

        def __repr__(self):
            return "Value(value={}, unifier={})".format(
                repr(self.value), repr(self.unifier))

    class Undo(object):
        def __init__(self, var, unifier):
            self.var = var
            self.unifier = unifier

        def __str__(self):
            return "<var: {}, unifier: {}>".format(
                str(self.var), str(self.unifier))

        def __eq__(self, other):
            return self.var == other.var and self.unifier == other.unifier

    def __init__(self, dictionary=None):
        # each value is a Value
        self.contents = {}
        if dictionary is not None:
            for var, value in dictionary.iteritems():
                self.add(var, value, None)

    def add(self, var, value, unifier):
        value = self.Value(value, unifier)
        # logging.debug("Adding {} -> {} to unifier {}".format(
        #      str(var), str(value), str(self)))
        self.contents[var] = value
        return self.Undo(var, self)

    def delete(self, var):
        if var in self.contents:
            del self.contents[var]

    def value(self, term):
        if term in self.contents:
            return self.contents[term]
        else:
            return None

    def apply(self, term, caller=None):
        return self.apply_full(term, caller=caller)[0]

    def apply_full(self, term, caller=None):
        """ Recursively apply unifiers to TERM and return
            (i) the final value and (ii) the final unifier.
            If the final value is a variable, instantiate
            with a new variable if not in KEEP_VARS """
        # logging.debug("apply_full({}, {})".format(str(term), str(self)))
        val = self.value(term)
        if val is None:
            # If result is a variable and this variable is not one of those
            #   in the top-most calling context, then create a new variable
            #   name based on this Binding.
            # This process avoids improper variable capture.
            #   Outputting the same variable with the same binding twice will
            #   generate the same output, but outputting the same variable with
            #   different bindings will generate different outputs.
            # Note that this variable name mangling
            #   is not done for the top-most variables,
            #   which makes output a bit easier to read.
            # Unfortunately, the process is non-deterministic from one run
            #   to the next, which makes testing difficult.
            if (caller is not None and term.is_variable() and
                    not (term in caller.variables and caller.binding is self)):
                return (compile.Variable(term.name + str(id(self))), self)
            else:
                return (term, self)
        elif val.unifier is None or not val.value.is_variable():
            return (val.value, val.unifier)
        else:
            return val.unifier.apply_full(val.value)

    def is_one_to_one(self):
        image = set()  # set of all things mapped TO
        for x in self.contents:
            val = self.apply(x)
            if val in image:
                return False
            image.add(val)
        return True

    def __str__(self):
        s = repr(self)
        s += "={"
        s += ",".join(["{}:{}".format(str(var), str(val))
            for var, val in self.contents.iteritems()])
        s += "}"
        return s

    def recur_str(self):
        s = repr(self)
        s += "={"
        s += ",".join(["{}:{}".format(var, val.recur_str())
            for var, val in self.contents.iteritems()])
        s += "}"
        return s

    def __eq__(self, other):
        return self.contents == other.contents

def binding_str(binding):
    """ Handles string conversion of either dictionary or Unifier. """
    if isinstance(binding, dict):
        s = ",".join(["{}: {}".format(str(var), str(val))
            for var, val in binding.iteritems()])
        return '{' + s + '}'
    else:
        return str(binding)

def undo_all(changes):
    """ Undo all the changes in CHANGES. """
    # logging.debug("undo_all({})".format(
    #     "[" + ",".join([str(x) for x in changes]) + "]"))
    for change in changes:
        if change.unifier is not None:
            change.unifier.delete(change.var)

def bi_unify_atoms(atom1, unifier1, atom2, unifier2):
    """ If possible, modify BiUnifier UNIFIER1 and BiUnifier UNIFIER2 so that
        ATOM1.plug(UNIFIER1) == ATOM2.plug(UNIFIER2).
        Returns None if not possible; otherwise, returns
        a list of changes to unifiers that can be undone
        with undo-all. May alter unifiers besides UNIFIER1 and UNIFIER2. """
    # logging.debug("Unifying {} under {} and {} under {}".format(
    #      str(atom1), str(unifier1), str(atom2), str(unifier2)))
    if atom1.table != atom2.table:
        return None
    if len(atom1.arguments) != len(atom2.arguments):
        return None
    changes = []
    for i in xrange(0, len(atom1.arguments)):
        assert isinstance(atom1.arguments[i], compile.Term)
        assert isinstance(atom2.arguments[i], compile.Term)
        # grab values for args
        val1, binding1 = unifier1.apply_full(atom1.arguments[i])
        val2, binding2 = unifier2.apply_full(atom2.arguments[i])
        # logging.debug("val({})={} at {}, val({})={} at {}".format(
        #     str(atom1.arguments[i]), str(val1), str(binding1),
        #     str(atom2.arguments[i]), str(val2), str(binding2)))
        # assign variable (if necessary) or fail
        if val1.is_variable() and val2.is_variable():
            # logging.debug("1 and 2 are variables")
            if bi_var_equal(val1, binding1, val2, binding2):
                continue
            else:
                changes.append(binding1.add(val1, val2, binding2))
        elif val1.is_variable() and not val2.is_variable():
            # logging.debug("Left arg is a variable")
            changes.append(binding1.add(val1, val2, binding2))
        elif not val1.is_variable() and val2.is_variable():
            # logging.debug("Right arg is a variable")
            changes.append(binding2.add(val2, val1, binding1))
        elif val1 == val2:
            continue
        else:
            # logging.debug("Unify failure: undoing")
            undo_all(changes)
            return None
    return changes

# def plug(atom, binding, withtable=False):
#     """ Returns a tuple representing the arguments to ATOM after having
#         applied BINDING to the variables in ATOM. """
#     if withtable is True:
#         result = [atom.table]
#     else:
#         result = []
#     for i in xrange(0, len(atom.arguments)):
#         if atom.arguments[i].is_variable() and atom.arguments[i].name in binding:
#             result.append(binding[atom.arguments[i].name])
#         else:
#             result.append(atom.arguments[i].name)
#     return tuple(result)

def match_tuple_atom(tuple, atom):
    """ Returns a binding dictionary that when applied to ATOM's arguments
        gives exactly TUPLE, or returns None if no such binding exists. """
    if len(tuple) != len(atom.arguments):
        return None
    binding = {}
    for i in xrange(0, len(tuple)):
        arg = atom.arguments[i]
        if arg.is_variable():
            if arg.name in binding:
                oldval = binding[arg.name]
                if oldval != tuple[i]:
                    return None
            else:
                binding[arg.name] = tuple[i]
    return binding

def bi_var_equal(var1, unifier1, var2, unifier2):
    """ Returns True iff variable VAR1 in unifier UNIFIER1 is the same
    variable as VAR2 in UNIFIER2. """
    return (var1 == var2 and unifier1 is unifier2)

def same(formula1, formula2):
    """ Determine if FORMULA1 and FORMULA2 are the same up to a variable
        renaming. Treats FORMULA1 and FORMULA2 as having different
        variable namespaces. Returns None or the pair of unifiers. """
    logging.debug("same({}, {})".format(str(formula1), str(formula2)))
    if isinstance(formula1, compile.Atom):
        if isinstance(formula2, compile.Rule):
            return None
        else:
            u1 = BiUnifier()
            u2 = BiUnifier()
            if same_atoms(formula1, u1, formula2, u2, set()) is not None:
                return (u1, u2)
            return None
    elif isinstance(formula1, compile.Rule):
        if isinstance(formula2, compile.Atom):
            return None
        else:
            if len(formula1.body) != len(formula2.body):
                return None
            u1 = BiUnifier()
            u2 = BiUnifier()
            bound2 = set()
            result = same_atoms(formula1.head, u1, formula2.head, u2, bound2)
            if result is None:
                return None
            for i in xrange(0, len(formula1.body)):
                result = same_atoms(
                    formula1.body[i], u1, formula2.body[i], u2, bound2)
                if result is None:
                    return None
            return (u1, u2)
    else:
        return None

def same_atoms(atom1, unifier1, atom2, unifier2, bound2):
    """ Modifies UNIFIER1 and UNIFIER2 to demonstrate
    that ATOM1 and ATOM2 are identical up to a variable renaming.
    Returns None if not possible or the list of changes if it is.
    BOUND2 is the set of variables already bound in UNIFIER2 """
    def die():
        undo_all(changes)
        return None
    logging.debug("same_atoms({}, {})".format(str(atom1), str(atom2)))
    if atom1.table != atom2.table:
        return None
    if len(atom1.arguments) != len(atom2.arguments):
        return None
    changes = []
    # logging.debug("same_atoms entering loop")
    for i in xrange(0, len(atom1.arguments)):
        val1, binding1 = unifier1.apply_full(atom1.arguments[i])
        val2, binding2 = unifier2.apply_full(atom2.arguments[i])
        # logging.debug("val1: {} at {}; val2: {} at {}".format(
        #     str(val1), str(binding1), str(val2), str(binding2)))
        if val1.is_variable() and val2.is_variable():
            if bi_var_equal(val1, binding1, val2, binding2):
                continue
            # if we already bound either of these variables, not SAME
            if not bi_var_equal(val1, binding1, atom1.arguments[i], unifier1):
                # logging.debug("same_atoms: arg1 already bound")
                return die()
            if not bi_var_equal(val2, binding2, atom2.arguments[i], unifier2):
                # logging.debug("same_atoms: arg2 already bound")
                return die()
            if val2 in bound2:
                # logging.debug("same_atoms: binding is not 1-1")
                return die()
            changes.append(binding1.add(val1, val2, binding2))
            bound2.add(val2)
        elif val1.is_variable():
            # logging.debug("val1 is a variable")
            return die()
        elif val2.is_variable():
            # logging.debug("val2 is a variable")
            return die()
        elif val1 != val2:
            # one is a variable and one is not or unmatching object constants
            # logging.debug("val1 != val2")
            return die()
    return changes

def instance(formula1, formula2):
    """ Determine if FORMULA1 is an instance of FORMULA2, i.e. if there is
        some binding that when applied to FORMULA1 results in FORMULA2.
        Returns None or a unifier. """
    logging.debug("instance({}, {})".format(str(formula1), str(formula2)))
    if isinstance(formula1, compile.Atom):
        if isinstance(formula2, compile.Rule):
            return None
        else:
            u = BiUnifier()
            if instance_atoms(formula1, formula2, u) is not None:
                return u
            return None
    elif isinstance(formula1, compile.Rule):
        if isinstance(formula2, compile.Atom):
            return None
        else:
            if len(formula1.body) != len(formula2.body):
                return None
            u = BiUnifier()
            result = instance_atoms(formula1.head, formula2.head, u)
            if result is None:
                return None
            for i in xrange(0, len(formula1.body)):
                result = same_atoms(
                    formula1.body[i], formula2.body[i], u)
                if result is None:
                    return None
            return u
    else:
        return None

def instance_atoms(atom1, atom2, unifier2):
    """ Adds bindings to UNIFIER2 to make ATOM1 equal to ATOM2
        after applying UNIFIER2 to ATOM2 only.   Returns None if
        no such bindings make equality hold. """
    def die():
        undo_all(changes)
        return None
    logging.debug("instance_atoms({}, {})".format(str(atom1), str(atom2)))
    if atom1.table != atom2.table:
        return None
    if len(atom1.arguments) != len(atom2.arguments):
        return None
    unifier1 = BiUnifier()
    changes = []
    for i in xrange(0, len(atom1.arguments)):
        val1, binding1 = unifier1.apply_full(atom1.arguments[i])
        val2, binding2 = unifier2.apply_full(atom2.arguments[i])
        # logging.debug("val1: {} at {}; val2: {} at {}".format(
        #     str(val1), str(binding1), str(val2), str(binding2)))
        if val1.is_variable() and val2.is_variable():
            if bi_var_equal(val1, binding1, val2, binding2):
                continue
            # if we already bound either of these variables, not INSTANCE
            if not bi_var_equal(val1, binding1, atom1.arguments[i], unifier1):
                # logging.debug("instance_atoms: arg1 already bound")
                return die()
            if not bi_var_equal(val2, binding2, atom2.arguments[i], unifier2):
                # logging.debug("instance_atoms: arg2 already bound")
                return die()
            # add binding to UNIFIER2
            changes.append(binding2.add(val2, val1, binding1))
        elif val1.is_variable():
            return die()
        elif val2.is_variable():
            changes.append(binding2.add(val2, val1, binding1))
            # logging.debug("var2 is a variable")
        elif val1 != val2:
            # unmatching object constants
            # logging.debug("val1 != val2")
            return die()
    return changes


def skolemize(formulas):
    """ Given a list of formulas, instantiate all variables
        consistently with UUIDs. """
    # create binding then plug it in.
    variables = set()
    for formula in formulas:
        variables |= formula.variables()

    binding = {}
    for var in variables:
        binding[var] = compile.Term.create_from_python(str(uuid.uuid4()))

    return [formula.plug(binding) for formula in formulas]