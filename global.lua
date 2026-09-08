-- Pili Pili - Tabletop Simulator table script
--
-- Everything lives on the table: a chilli button in the middle that runs the
-- round, a +/- dibber in front of each seat for that player's bet, a mat where
-- you stack the tricks you win, and a tray your Pilis land in.
--
-- The button never has to work out who won a trick. Every trick holds exactly
-- one card per player, so tricks won = cards in your pile / number of players.
-- That keeps the missions that rewrite trick resolution (Upside Down and the
-- rest) entirely out of the script's business.

TAG_PLAY = "PILI:PLAY"
TAG_MISSION = "PILI:MISSION"
TAG_DIBBER = "PILI:DIBBER:"
TAG_TRICKS = "PILI:TRICKS:"
TAG_PILIS = "PILI:PILIS:"
TAG_MAT = "PILI:MAT:"
TAG_TRAY = "PILI:TRAY:"
TAG_BUTTON = "PILI:BUTTON"
TAG_DEALER = "PILI:DEALER"
TAG_MTOGGLE = "PILI:MTOGGLE"

-- POS_PLAY, POS_ASIDE, POS_MISSION, POS_REVEAL and POS_DISCARD are injected
-- above this line by build_save.py, from the same constants that place the
-- objects in the save. Do not redeclare them here or they will drift apart.

PILI_LIMIT = 6

GOLD = {0.91, 0.77, 0.36}
HOT = {1.0, 0.38, 0.32}
COOL = {0.55, 0.85, 0.65}

bids = {}          -- colour -> bet, nil until that player touches their dibber
dealt = 0          -- cards dealt each this round
busy = false       -- guard, the round sequence is asynchronous
missionsOn = false -- off by default - the rulebook's own suggested first game
                   -- skips missions entirely; flip the tile by the mission
                   -- deck to turn them on

-- ------------------------------------------------------------------ state --

function onSave()
    return JSON.encode({bids = bids, dealt = dealt, missionsOn = missionsOn})
end

function onLoad(state)
    if state ~= nil and state ~= "" then
        local ok, s = pcall(function() return JSON.decode(state) end)
        if ok and s ~= nil then
            bids = s.bids or {}
            dealt = s.dealt or 0
            missionsOn = s.missionsOn or false
        end
    end
    Wait.time(buildControls, 0.6)
end

-- ------------------------------------------------------------------ finding --

function tagged(tag, exact)
    local out = {}
    for _, o in ipairs(getAllObjects()) do
        local n = o.getGMNotes()
        if n ~= nil and n ~= "" then
            if (exact and n == tag) or (not exact and string.sub(n, 1, #tag) == tag) then
                table.insert(out, o)
            end
        end
    end
    return out
end

function one(tag)
    return tagged(tag, true)[1]
end

function seatOf(obj, prefix)
    return string.sub(obj.getGMNotes(), #prefix + 1)
end

function cardsTagged(tag)
    local out = {}
    for _, o in ipairs(getAllObjects()) do
        local t = o.type
        if (t == "Card" or t == "Deck") and o.getGMNotes() == tag then
            table.insert(out, o)
        end
    end
    return out
end

function countIn(o)
    if o.type == "Deck" then return #o.getObjects() end
    return 1
end

function biggest(tag)
    local best, n = nil, -1
    for _, o in ipairs(cardsTagged(tag)) do
        local c = countIn(o)
        if c > n then best, n = o, c end
    end
    return best
end

function seatedSet()
    local s = {}
    for _, c in ipairs(getSeatedPlayers()) do s[c] = true end
    return s
end

-- ------------------------------------------------------------------ controls --

function buildControls()
    for _, d in ipairs(tagged(TAG_DIBBER, false)) do
        d.clearButtons()
        local colour = seatOf(d, TAG_DIBBER)
        d.createButton({
            click_function = "bidDown", function_owner = Global, label = "-",
            position = {-0.62, 0.3, 0.10}, width = 320, height = 320,
            font_size = 260, color = {0.55, 0.10, 0.09}, font_color = {1, 1, 1},
            tooltip = colour .. ": one fewer trick",
        })
        d.createButton({
            click_function = "bidNudge", function_owner = Global,
            label = bidLabel(colour),
            position = {0.0, 0.3, 0.10}, width = 520, height = 320,
            font_size = 260, color = {0.10, 0.09, 0.09}, font_color = {1, 0.95, 0.8},
            tooltip = colour .. "'s bet",
        })
        d.createButton({
            click_function = "bidUp", function_owner = Global, label = "+",
            position = {0.62, 0.3, 0.10}, width = 320, height = 320,
            font_size = 260, color = {0.55, 0.10, 0.09}, font_color = {1, 1, 1},
            tooltip = colour .. ": one more trick",
        })
    end

    local b = one(TAG_BUTTON)
    if b ~= nil then
        b.clearButtons()
        b.createButton({
            click_function = "nextRound", function_owner = Global, label = "",
            position = {0, 0.3, 0}, width = 1500, height = 700,
            color = {0, 0, 0, 0},
            tooltip = "Score this round, reshuffle, new mission, deal",
        })
    end

    local mt = one(TAG_MTOGGLE)
    if mt ~= nil then
        mt.clearButtons()
        mt.createButton({
            click_function = "toggleMissions", function_owner = Global,
            label = missionsLabel(),
            position = {0, 0.3, 0.05}, width = 900, height = 380,
            font_size = 260, color = {0.12, 0.11, 0.09}, font_color = {1, 0.95, 0.8},
            tooltip = "Turn Mission cards on or off for future rounds",
        })
    end

    refreshDibbers()
end

function missionsLabel()
    if missionsOn then return "ON" end
    return "OFF"
end

function toggleMissions()
    missionsOn = not missionsOn
    local mt = one(TAG_MTOGGLE)
    if mt ~= nil then mt.editButton({index = 1, label = missionsLabel()}) end
    if missionsOn then
        broadcastToAll("Missions ON from the next round - the mission deck " ..
            "sets a special rule and how many cards are dealt.", GOLD)
    else
        broadcastToAll("Missions OFF from the next round - a plain deal of 5 " ..
            "cards each, straight to betting.", GOLD)
    end
end

function bidLabel(colour)
    local b = bids[colour]
    if b == nil then return "" end      -- blank until this seat has bet -
                                         -- "?" looked like a third minus
                                         -- button crammed between the real
                                         -- two, and read as upside-down
    return tostring(b)
end

function refreshDibbers()
    for _, d in ipairs(tagged(TAG_DIBBER, false)) do
        d.editButton({index = 1, label = bidLabel(seatOf(d, TAG_DIBBER))})
    end
end

-- ------------------------------------------------------------------ betting --

function bidNudge(obj, player_colour)
    broadcastToColor("Use - and + to set your bet.", player_colour, GOLD)
end

function bidUp(obj, player_colour) adjustBid(obj, player_colour, 1) end
function bidDown(obj, player_colour) adjustBid(obj, player_colour, -1) end

function adjustBid(obj, player_colour, delta)
    local seat = seatOf(obj, TAG_DIBBER)
    local p = Player[player_colour]
    if player_colour ~= seat and not (p ~= nil and p.admin) then
        broadcastToColor("That is " .. seat .. "'s dibber, not yours.", player_colour, HOT)
        return
    end
    if dealt <= 0 then
        broadcastToColor("Nothing dealt yet - press the chilli.", player_colour, HOT)
        return
    end

    local want = (bids[seat] or 0) + delta
    if want < 0 then want = 0 end
    if want > dealt then want = dealt end

    -- The bets must not total the cards dealt, and that binds whoever bets
    -- last. If everyone else has bet, this player is last, so refuse the one
    -- number that would make the totals match.
    local others, missing = 0, 0
    for c, _ in pairs(seatedSet()) do
        if c ~= seat then
            if bids[c] == nil then missing = missing + 1 else others = others + bids[c] end
        end
    end
    if missing == 0 and others + want == dealt then
        broadcastToAll(seat .. " is last to bet and cannot make the bets total " ..
            dealt .. " - there has to be a loser. Pick another number.", HOT)
        return
    end

    bids[seat] = want
    refreshDibbers()

    local total, unset = 0, 0
    for c, _ in pairs(seatedSet()) do
        if bids[c] == nil then unset = unset + 1 else total = total + bids[c] end
    end
    if unset == 0 then
        broadcastToAll("All bets are in - " .. total .. " tricks bet between " ..
            "you, " .. dealt .. " cards to play. Everyone plays one card " ..
            "to the middle each trick: highest number wins it and takes it, " ..
            "and whoever won leads (plays first) next. The dealer plays first " ..
            "card of all, since nobody has won a trick yet.", GOLD)
    end
end

-- ------------------------------------------------------------------ scoring --

function zoneCount(tag, colour)
    local z = one(tag .. colour)
    if z == nil then return 0 end
    local n = 0
    for _, o in ipairs(z.getObjects()) do
        if o.type == "Card" then
            n = n + 1
        elseif o.type == "Deck" then
            n = n + #o.getObjects()
        end
    end
    return n
end

function piliCount(colour)
    local z = one(TAG_PILIS .. colour)
    if z == nil then return 0 end
    local n = 0
    for _, o in ipairs(z.getObjects()) do
        if o.getGMNotes() == "PILI:TOKEN" then n = n + 1 end
    end
    return n
end

function scoreRound()
    local seated = getSeatedPlayers()
    if dealt <= 0 or #seated == 0 then return end

    local bag = one("PILI:BAG")
    local lines = {}
    for _, c in ipairs(seated) do
        local cards = zoneCount(TAG_TRICKS, c)
        local tricks = math.floor(cards / #seated + 0.5)
        local bet = bids[c]
        if bet == nil then
            table.insert(lines, c .. " never bet")
        else
            local owed = math.abs(bet - tricks)
            if owed == 0 then
                table.insert(lines, c .. " bet " .. bet .. ", took " .. tricks .. " - clean")
            else
                table.insert(lines, c .. " bet " .. bet .. ", took " .. tricks ..
                    " - " .. owed .. " Pili" .. (owed == 1 and "" or "s"))
                givePilis(c, owed, bag)
            end
        end
    end
    broadcastToAll(table.concat(lines, "\n"), GOLD)
end

function givePilis(colour, n, bag)
    local z = one(TAG_PILIS .. colour)
    if bag == nil or z == nil then return end
    local p = z.getPosition()
    for i = 1, n do
        Wait.time(function()
            bag.takeObject({
                position = {p.x + math.random() * 0.9 - 0.45, p.y + 1.5 + i * 0.3,
                            p.z + math.random() * 0.9 - 0.45},
                rotation = {0, math.random(0, 359), 0}, smooth = true,
            })
        end, 0.12 * i)
    end
end

function checkGameOver()
    local worst, hits = 0, {}
    for _, c in ipairs(getSeatedPlayers()) do
        local n = piliCount(c)
        if n > worst then worst = n end
        if n >= PILI_LIMIT then table.insert(hits, c) end
    end
    if #hits == 0 then return false end

    local best = 9999
    for _, c in ipairs(getSeatedPlayers()) do
        best = math.min(best, piliCount(c))
    end
    local winners = {}
    for _, c in ipairs(getSeatedPlayers()) do
        if piliCount(c) == best then table.insert(winners, c) end
    end
    broadcastToAll(table.concat(hits, " & ") .. " reached " .. PILI_LIMIT ..
        " Pilis - game over. Fewest Pilis: " .. table.concat(winners, " & ") ..
        " on " .. best .. ".", HOT)
    return true
end

-- ------------------------------------------------------------------ round --

-- Reported bug: the play deck kept sliding off the table. It was resting in
-- the dealer's open cut-out (see the POS_* comment in build_save.py) with no
-- anchor, so any nearby physics nudge could walk it toward the unrailed edge
-- and off. Locking it at rest stops that; anything that will shuffle/deal/
-- take from a locked object needs to unlock it first, since Locked blocks
-- player drag but scripted calls are unaffected either way - unlocking is
-- just defensive.
function lockAtRest(obj)
    if obj ~= nil then obj.Locked = true end
end

function unlockForOps(obj)
    if obj ~= nil then obj.Locked = false end
end

function gather(tag, pos, thenShuffle, callback)
    local objs = cardsTagged(tag)
    if #objs == 0 then
        if callback then callback() end
        return
    end
    local base = table.remove(objs, 1)
    unlockForOps(base)
    base.setPosition({pos[1], pos[2] + 3.0, pos[3]})
    base.setRotation({0, 180, 180})
    for _, o in ipairs(objs) do
        unlockForOps(o)
        local r = base.putObject(o)
        if r ~= nil then base = r end
    end
    Wait.time(function()
        if base ~= nil then
            base.setGMNotes(tag)
            if thenShuffle and base.type == "Deck" then base.shuffle() end
            base.setPositionSmooth(pos)
            base.setRotationSmooth({0, 180, 180})
            Wait.time(function() lockAtRest(base) end, 1.0)
        end
        if callback then callback() end
    end, 1.1)
end

function nextRound()
    if busy then return end
    local seated = getSeatedPlayers()
    if #seated == 0 then
        broadcastToAll("Nobody is seated in a player colour.", HOT)
        return
    end
    busy = true

    if dealt > 0 then
        scoreRound()
    end

    Wait.time(function()
        if dealt > 0 and checkGameOver() then
            busy = false
            dealt = 0
            bids = {}
            refreshDibbers()
            return
        end
        sweepAndDeal(seated)
    end, dealt > 0 and 1.6 or 0.1)
end

function sweepAndDeal(seated)
    -- old mission out of the way, if one was in play
    local live = missionInPlay()
    if live ~= nil then
        live.setPositionSmooth(POS_DISCARD)
        live.setRotationSmooth({0, 180, 180})
    end

    if not missionsOn then
        -- rulebook's own suggested first game: skip missions, deal 5 each,
        -- straight to betting. The mission deck is left completely alone.
        gather(TAG_PLAY, POS_PLAY, true, function()
            dealCards(seated, nil, 5)
        end)
        return
    end

    gather(TAG_PLAY, POS_PLAY, true, function()
        local mdeck = biggest(TAG_MISSION)
        if mdeck == nil then
            broadcastToAll("No mission cards left.", HOT)
            busy = false
            return
        end
        unlockForOps(mdeck)
        if mdeck.type == "Deck" then
            mdeck.takeObject({position = POS_REVEAL, rotation = {0, 180, 0}, smooth = true})
        else
            mdeck.setPositionSmooth(POS_REVEAL)
            mdeck.setRotationSmooth({0, 180, 0})
        end
        Wait.time(function() lockAtRest(biggest(TAG_MISSION)) end, 1.0)

        Wait.time(function()
            local m = missionInPlay()
            local n = 5
            if m ~= nil then
                n = tonumber(string.match(m.getDescription(), "%[deal (%d+)%]")) or 5
            end
            local name = m and m.getName() or "no mission"
            dealCards(seated, name, n)
        end, 1.4)
    end)
end

function missionInPlay()
    local best, bestd = nil, 1e9
    for _, o in ipairs(cardsTagged(TAG_MISSION)) do
        if o.type == "Card" then
            local p = o.getPosition()
            local d = (p.x - POS_REVEAL[1]) ^ 2 + (p.z - POS_REVEAL[3]) ^ 2
            if d < bestd then best, bestd = o, d end
        end
    end
    if bestd > 30 then return nil end
    return best
end

function dealCards(seated, missionName, n)
    local deck = biggest(TAG_PLAY)
    if deck == nil or deck.type ~= "Deck" then
        broadcastToAll("The play deck did not come back together.", HOT)
        busy = false
        return
    end
    unlockForOps(deck)

    local avail = countIn(deck)
    local maxn = math.floor(avail / #seated)
    if n > maxn then
        broadcastToAll("Only " .. avail .. " cards for " .. #seated ..
            " players - dealing " .. maxn .. " each instead of " .. n .. ".", HOT)
        n = maxn
    end
    if n < 1 then
        broadcastToAll("Too many players for the cards available.", HOT)
        busy = false
        return
    end

    dealt = n
    bids = {}
    refreshDibbers()
    deck.shuffle()

    Wait.time(function()
        deck.deal(n)
        Wait.time(function()
            -- leftovers are set aside face down, still reachable for the
            -- missions that draw an extra card
            local rest = biggest(TAG_PLAY)
            if rest ~= nil then
                rest.setPositionSmooth(POS_ASIDE)
                rest.setRotationSmooth({0, 180, 180})
                Wait.time(function() lockAtRest(biggest(TAG_PLAY)) end, 1.0)
            end
            passDealer()

            local label = missionName and ("Mission: " .. missionName .. ".  ")
                or ""
            broadcastToAll(label .. n .. " cards each. Starting with the " ..
                "dealer, everyone bets how many of their " .. n ..
                " tricks they think they will win - use the -/+ on your " ..
                "own dibber.", GOLD)
            busy = false
        end, 1.0)
    end, 0.6)
end

-- ------------------------------------------------------------------ dealer --

function passDealer()
    local marker = one(TAG_DEALER)
    if marker == nil then return end
    local seated = getSeatedPlayers()
    if #seated == 0 then return end

    -- SEAT_ORDER is injected at build time from the SEATS table, so it is the
    -- real seating order round the table rather than whatever order TTS
    -- happens to hand back from getSeatedPlayers().
    local order = SEAT_ORDER
    if order == nil or #order == 0 then order = seated end

    -- nearest seat to the marker now, then step to the next seated colour
    local here, bestd = nil, 1e9
    local p = marker.getPosition()
    for _, c in ipairs(order) do
        local z = one(TAG_DIBBER .. c)
        if z ~= nil then
            local q = z.getPosition()
            local d = (p.x - q.x) ^ 2 + (p.z - q.z) ^ 2
            if d < bestd then here, bestd = c, d end
        end
    end

    local idx = 1
    for i, c in ipairs(order) do
        if c == here then idx = i end
    end
    local seatedNow = seatedSet()
    local nxt = nil
    for step = 1, #order do
        local c = order[((idx - 1 + step) % #order) + 1]
        if seatedNow[c] then nxt = c; break end
    end
    if nxt == nil then return end

    local z = one(TAG_DIBBER .. nxt)
    if z ~= nil then
        local q = z.getPosition()
        marker.setPositionSmooth({q.x, q.y + 1.2, q.z})
    end
    Turns.turn_color = nxt
    broadcastToAll(nxt .. " is dealer this round: " .. nxt ..
        " bets first, and plays the first card once betting is done.", COOL)
end
