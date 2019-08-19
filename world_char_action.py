
import random, traceback, copy
import hou

# concrete action - their abstract actions are defined in action hda
class Action():
    def __init__(self, abstract_action, world, bindings):
        self.action = abstract_action
        self.world = world
        self.bindings = bindings
        self.timestep = -1
        self.c_index = -1
        self.was_done = False
        self.causes = []
        self.caused = []
    def __repr__(self):
        ret = self.action.name
        if self.bindings.has_key("initiator"):
            me = self.bindings["initiator"]
            ret += " by " + str(me)# TODO: make this available per action
        ret += " at ts " + str(self.timestep) + " - chronicle_index " + str(self.c_index)
        if not self.was_done:
            ret += " (not done yet)"
        for bi in self.bindings:
            if bi not in ["initiator", "participants", "optional"] :
                if self.bindings[bi] != []:
                    ret += "\n\t("+bi+": " + str(self.bindings[bi]) + ")"
        return ret + "\n"
    def execute(self):
        assert not self.was_done, "Action should not have been done already"
        a = self.action
        w = self.world
        b = self.bindings
        self.c_index = len(w.chronicle)
        me = b["initiator"]
        for c in b["participants"]:
            if a in c.queued_actions:
                c.queued_actions.remove(a)
        self.executed_effects = []
        for it, e in enumerate(a.effects):
            precond_results = [] 
            try:
                exec(e.preconditions)
                precond_results = exec_out
            except Exception as ex:
                error_text = "\n" + traceback.format_exc() + \
                    "\tin preconditions of effect " + str(it) + " of action\n\t'" + \
                    a.name + "' (defined at " + a.hou_path + "):\n" + e.preconditions
                print error_text
                assert False, error_text
            assert len(precond_results) == e.preconditions.count(",")+1, "assuming commas delineate preconditions nicely"
            precond_texts = e.preconditions.split(",")
            if all(precond_results):
                try:
                    exec(e.effect)
                    self.executed_effects.append(str(it) + ": " + e.effect + "; randoms: " + str(randoms))
                except Exception as ex:
                    error_text = "\n" + traceback.format_exc() + \
                        "\tin effect " + str(it) + " of action\n\t'" + \
                        a.name + "' (defined at " + a.hou_path + "):\n" + e.effect
                    print error_text
                    assert False, error_text
        # track causality for bound action
        if "action" in b and b["action"] != None:
            b["action"].caused.append(self)
            self.causes.append(b["action"])
        self.timestep = w.timestep
        self.was_done = True
        
        # add knol of action index in chronicle, with salience per role
        saliences_by_role = {r["name"]: r["action_salience"] for r in a.roles}
        for c in b["participants"]:
            knowledge_salience = 0
            for k in hs.people_roles:
                if k == "initiator":
                    if b[k] == c:
                        knowledge_salience = saliences_by_role[k]
                        break
                elif c in b[k]:
                    knowledge_salience = saliences_by_role[k]
                    break
            if c.knols.has_key(self.c_index):
                c.knols[self.c_index] = max(c.knols[self.c_index], knowledge_salience)
            else:
                c.knols[self.c_index] = knowledge_salience
    
class World():
    def __init__(self, start_timestep=0, end_timestep=2, debug_level = 1):
        self.start_timestep = start_timestep
        self.end_timestep = end_timestep
        self.timestep = start_timestep
        self.next_timestep_len = -1
        self.day = 0
        self.year = 0
        self.n_actions_allowed = 10
        self.action_attempts_per_char = 10
        self.debug_level = debug_level
        
        self.characters = []
        self.action_names = []
        self.chronicle = []
        
    def __repr__(self):
        ret = """World with {0} characters and {1} actions in chronicle
        at ts {2} (year {3} day {4})""".format(len(self.characters), len(self.chronicle),
        self.timestep, self.year, self.day)
        return ret
        
    def evaluate_role_preconditions(self, r, action_to_queue, me = None):
        a = action_to_queue.action
        b = action_to_queue.bindings
        init = None
        if "initiator" in b:
            if me == None:
                me = b["initiator"]
            init = b["initiator"]
        w = self
        
        precondition_results, randoms = [[],[]]
        try:
            exec(r["preconditions"])
            precondition_results = exec_out
        except Exception as ex:
                    error_text = "\n" + traceback.format_exc() + \
                        " in preconditions of " + r["name"] + " role " + r["index"] + " of action\n\t'" + \
                        a.name + "' (defined at " + a.hou_path + "):\n" + r["preconditions"]
                    print error_text
                    assert False, error_text
        assert len(precondition_results) == r["preconditions"].count(",")+1, "assuming commas delineate preconditions nicely"
        
        return all(precondition_results)
        
    def get_role_candidate_pool(self, r, action_to_queue):
        a = action_to_queue.action
        b = action_to_queue.bindings
        me = None
        if "initiator" in b:
            me = b["initiator"]
        w = self
        candidate_pool, randoms = [[],[]]
        try:
            exec(r["candidate_pool_directive"])
            candidate_pool = exec_out
        except Exception as ex:
                    error_text = "\n" + traceback.format_exc() + \
                        " in candidate pool directive of " + r["name"] + " role " + r["index"] + " of action\n\t'" + \
                        a.name + "' (defined at " + a.hou_path + "):\n" + r["candidate_pool_directive"]
                    print error_text
                    assert False, error_text
        return candidate_pool
        
    def target_action(self, attempts_per_character=10):
        if len(self.actors_pool) == 0:
            return None
        random.shuffle(self.actors_pool)
        random_actor = self.actors_pool[0]     
        actor_found_generic_action = False
        not_attempted_action_names = [i for i in hs.generic_action_names if i in self.action_names]
        for i in range(attempts_per_character):
            if len(not_attempted_action_names) == 0:
                break
            an = random.choice(not_attempted_action_names)
            
            not_attempted_action_names.remove(an)
            ab = hs.abstract_actions[an]
            
            # evaluate initiator preconditions
            initiator_roles = [r for r in ab.roles if r["name"] == "initiator"]
            assert len(initiator_roles) == 1, "for now, 1 initiator is required - " + an
            initiator_role = initiator_roles[0]
            ac = Action(ab, self, {})
            
            # assume each role other than initiator may have multiple number, so is a list
            for r in ab.roles:
                if not r["name"] == "initiator":
                    ac.bindings[r["name"]] = []
            ac.bindings["participants"] = []
            ac.bindings["optional"] = []
            
            if random_actor in self.get_role_candidate_pool (initiator_role, ac) and \
                    self.evaluate_role_preconditions(initiator_role, ac, random_actor):
                ac.bindings["initiator"] = random_actor
                self.actors_pool.pop(0) # remove chosen actor from pool
                ac.bindings["participants"].append(ac.bindings["initiator"])
                #randomly assemble minimal bindings
                if self.complete_bindings(ac):
                    # found targeted role
                    return ac
        if random_actor not in self.actors_pool:
            self.actors_pool.append(random_actor) # if we couldn't find an initiator role, at least he can be a different role
        return None
        
    def queue_actions(self):
        self.step(self.next_timestep_len)
        # TODO handle dead chars
        self.actors_pool = self.characters[:]
        num_actions_queued = 0
        for j in range(self.n_actions_allowed):
            ac = self.target_action(self.action_attempts_per_char)
            if ac:
                for c in ac.bindings["participants"]:
                    c.queued_actions.append(ac)
                num_actions_queued +=1
        #print num_actions_queued

    def complete_bindings(self, ac):
        assert "initiator" in ac.bindings, "an action initiator is required for " + str(ac)
        
        # first ensure standard bindings exist
        for r in ac.action.roles:
            if not r["name"] == "initiator":
                if r["name"] not in ac.bindings:
                    ac.bindings[r["name"]] = []
        if "participants" not in ac.bindings:
            ac.bindings["participants"] = []
        if "optional" not in ac.bindings:
            ac.bindings["optional"] = []

        for r in ac.action.roles:
            if r["name"] in hs.people_roles:
                if r["name"] == "initiator":
                    if ac.bindings["initiator"] not in ac.bindings["participants"]:
                        ac.bindings["participants"].append(ac.bindings["initiator"])
                    continue
                for c in ac.bindings[r["name"]]:
                    if c not in ac.bindings["participants"]:
                        ac.bindings["participants"].append(c)

        # now fill all required roles laid out in the abstract action, except any pre-placed ones
        required_roles = [r for r in ac.action.roles if r["number_min"] > 0]
        roles_werent_filled = False
        for r in required_roles:
            if r["name"] == "initiator":
                if not self.evaluate_role_preconditions(r, ac, ac.bindings["initiator"]):
                    if self.debug_level > 1:
                        assert False, "the initiator does not satisfy the preconditions: " + str(ac.bindings["initiator"])
                    return False
                continue # the initiator was already part of the bindings
            
            # if any pre-filled required participants do not fulfil the preconditions, 
            # there may be edge cases where the action cannot be completed. For now
            # the role candidate pool is ignored so we can insert non-characters
            for c in ac.bindings[r["name"]]:
                if not self.evaluate_role_preconditions(r, ac, c):
                    if self.debug_level > 1:
                        assert False, "the " + r["name"] + " does not satisfy the preconditions: " + str(c)
                    # TODO: distinguish between optional and required pre-filled participants
                    return False
            num_to_fill = r["number_min"]
            num_to_fill -= len(ac.bindings[r["name"]])
            for n in range(num_to_fill):
                has_cand = False
                # evaluate required role preconditions
                for c in self.get_role_candidate_pool (r, ac):
                    if not c in ac.bindings["participants"]:
                        if self.evaluate_role_preconditions(r, ac, c):
                            ac.bindings[r["name"]].append(c)
                            if r["name"] in hs.people_roles:
                                ac.bindings["participants"].append(c)
                            has_cand = True
                            break
                if not has_cand:
                    roles_werent_filled = True
                    break
        if not roles_werent_filled:
            # for each optional role
            optional_roles = [r for r in ac.action.roles if r["number_max"] > r["number_min"]]
            
            for r in optional_roles:
                n_potential_additions = r["number_max"] - len(ac.bindings[r["name"]])
                for n in range(n_potential_additions):
                    if random.random() <= r["casting_chance"]:
                        for c in self.get_role_candidate_pool (r, ac):
                            if not c in ac.bindings["participants"]:
                                if self.evaluate_role_preconditions(r, ac):
                                    if r["name"] in hs.people_roles:
                                        ac.bindings["participants"].append(c)
                                        ac.bindings["optional"].append(c)
                                    ac.bindings[r["name"]].append(c)
                                    break
            
            return True
        return False
                    
    def execute_actions(self):
        self.actions_this_timestep = []
        potential_actions = []
        for c in self.characters:
            for ac in c.queued_actions:
                if ac.timestep == -1 or ac.timestep == self.timestep:
                    assert not ac.was_done, "Action should not have happened yet " + str(ac)
                    if not ac in potential_actions:
                        potential_actions.append(ac)
        # sort by urgency, then priority (higher comes first)
        potential_actions.sort(cmp=lambda x, y: (x.action.urgency*10000+x.action.priority<y.action.urgency*10000+y.action.priority)*2-1)
        n_p_actions = len(potential_actions)

        to_remove = []
        for ac in potential_actions:
            prev_bindings = copy.deepcopy(ac.bindings)
            if not self.complete_bindings(ac):
                to_remove.append(ac)
                ac.bindings = prev_bindings
        [potential_actions.remove(x) for x in potential_actions]

        # the most urgent/ important actions will be executed. If the characters involved are involved
        # in other actions this timestep, their actions will be delayed until after the urgent one is finished
        for i in range(n_p_actions):
            if len(potential_actions) == 0:
                break
            ac = potential_actions.pop(0)
            self.actions_this_timestep.append(ac)
            for ac2 in potential_actions:
                for c in ac.bindings["participants"]:
                    if c in ac2.bindings["participants"]:
                        if c not in ac2.bindings["optional"]:
                            potential_actions.remove(ac2)
                            # defer action until after first action completed
                            # maybe handle urgencies differently - do not defer non urgent actions?
                            if ac.timestep == -1:
                                ac.timestep = self.timestep
                            ac2.timestep += ac.action.duration
                            break
                        else: # remove optional character from action bindings
                            role_set = set(hs.people_roles + ["participants", "optional"])
                            role_set.remove("initiator") # not optional
                            for k in role_set:
                                if c in ac2.bindings[k]:
                                    ac2.bindings[k].remove(c)
        action_durations = []
        for ac in self.actions_this_timestep:
            # TODO: handle abandonment conditions, error codes
            ac.execute()
            if ac.action.duration != -1:
                action_durations.append(ac.action.duration)
            self.chronicle.append(ac)
        if action_durations == []:
            self.next_timestep_len = -1
        else:
            self.next_timestep_len = max(min(action_durations), 12)
        
    def step(self, hours=-1):
        if hours== -1:
            self.timestep = int(self.timestep)
            hours = 12
        self.timestep += hours/12.0
        if self.day < self.timestep/2:
            self.day += 1
            
            # characters' memories slowly fade every day
            for c in self.characters:
                #TODO: handle dead
                memories_to_remove = []
                for k in c.knols:
                    c.knols[k] -= 0.01
                    if c.knols[k] < 0:
                        memories_to_remove.append(k)
                for k in memories_to_remove:
                    c.knols.pop(k) # maybe don't remove memory for debug purposes
            
            if self.day%365 == 0:
                self.year += 1
                self.day = 0

class Character():
    def __init__(self, world):
        self.queued_actions = []
        self.knols = []
        self.world = world
    def __repr__(self):
        return self.first_name + " " + self.last_name
    def queue(self, action_name, cause, bindings={}, at_timestep=-1): # TODO: urgency, etc
        b = copy.deepcopy(bindings)
        if at_timestep == -1:
            at_timestep = self.world.timestep + cause.duration

        assert action_name in hs.abstract_actions, "Action not available: " + action_name
        ab = hs.abstract_actions[action_name]

        if "initiator" not in b:
            b["initiator"] = self.world.characters[self.char_index]
        ac = Action(ab, self.world, b)
        ac.causes.append(cause)
        self.queued_actions.append(ac)
        # TODO: maybe queue the action for all participants?
    
def get(p, a):
    return p.attribValue(a)

import json
def character_from_point(geo, p, world):
    c = Character(world)
    for v in geo.pointAttribs():
        if v.isArrayType():
            continue # a pain in the arse!
        if not "ladb_" in v.name(): # dont copy debug values
            if v.name().startswith("json_"):
                setattr( c, v.name().replace("json_", ""), json.loads(p.attribValue(v.name())))
            else:
                setattr( c, v.name(), p.attribValue(v.name()))
    return c
    
def character_to_point(geo, c, p):
    # cant create new point attribs via effects
    for v in geo.pointAttribs():
        if v.isArrayType():
            continue # a pain in the arse!
        if not "ladb_" in v.name(): # dont copy debug values
            #print v.name(),v.dataType(), type(getattr(c, v.name()))
            if v.name().startswith("json_"):
                p.setAttribValue(v.name(), json.dumps(getattr(c, v.name().replace("json_", ""))))
            else:
                val = getattr(c, v.name())
                if v.name()=="location":
                    val = int(val)
                #print v.name(), val, type(val)
                p.setAttribValue(v.name(), val)
                
hs = hou.session
hs.people_roles = ["initiator", "recipient", "bystander", "hearer"]
hs.character_from_point = character_from_point
hs.character_to_point = character_to_point
hs.Character = Character
hs.Action = Action
hs.World = World