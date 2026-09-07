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
TAG_BUTTON = "PILI:BUTTON"
TAG_DEALER = "PILI:DEALER"

POS_PLAY = {-6.2, 1.6, -2.8}
POS_ASIDE = {-6.2, 1.6, 2.8}
POS_MISSION = {6.2, 1.6, 2.8}
POS_REVEAL = {6.2, 1.6, -2.8}
POS_DISCARD = {0.0, 1.6, -3.4}

PILI_LIMIT = 6

GOLD = {0.91, 0.77, 0.36}
HOT = {1.0, 0.38, 0.32}
COOL = {0.55, 0.85, 0.65}

bids = {}          -- colour -> bet, nil until that player touches their dibber
dealt = 0          -- cards dealt each this round
busy = false       -- guard, the round sequence is asynchronous

-- ------------------------------------------------------------------ state --

function onSave()
    return JSON.encode({bids = bids, dealt = dealt})
end

function onLoad(state)
    if state ~= nil and state ~= "" then
        local ok, s = pcall(function() return JSON.decode(state) end)
        if ok and s ~= nil then
            bids = s.bids or {}
            dealt = s.dealt or 0
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
    refreshDibbers()
end

function bidLabel(colour)
    local b = bids[colour]
    if b == nil then return "-" end
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
        broadcastToAll("All bets in: " .. total .. " tricks bet, " .. dealt ..
            " to win. The dealer leads.", GOLD)
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

function gather(tag, pos, thenShuffle, callback)
    local objs = cardsTagged(tag)
    if #objs == 0 then
        if callback then callback() end
        return
    end
    local base = table.remove(objs, 1)
    base.setPosition({pos[1], pos[2] + 3.0, pos[3]})
    base.setRotation({0, 180, 180})
    for _, o in ipairs(objs) do
        local r = base.putObject(o)
        if r ~= nil then base = r end
    end
    Wait.time(function()
        if base ~= nil then
            base.setGMNotes(tag)
            if thenShuffle and base.type == "Deck" then base.shuffle() end
            base.setPositionSmooth(pos)
            base.setRotationSmooth({0, 180, 180})
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
    -- old mission out of the way
    local live = missionInPlay()
    if live ~= nil then
        live.setPositionSmooth(POS_DISCARD)
        live.setRotationSmooth({0, 180, 180})
    end

    gather(TAG_PLAY, POS_PLAY, true, function()
        local mdeck = biggest(TAG_MISSION)
        if mdeck == nil then
            broadcastToAll("No mission cards left.", HOT)
            busy = false
            return
        end
        if mdeck.type == "Deck" then
            mdeck.takeObject({position = POS_REVEAL, rotation = {0, 180, 0}, smooth = true})
        else
            mdeck.setPositionSmooth(POS_REVEAL)
            mdeck.setRotationSmooth({0, 180, 0})
        end

        Wait.time(function() dealFromMission(seated) end, 1.4)
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

function dealFromMission(seated)
    local m = missionInPlay()
    local n = 5
    if m ~= nil then
        n = tonumber(string.match(m.getDescription(), "%[deal (%d+)%]")) or 5
    end

    local deck = biggest(TAG_PLAY)
    if deck == nil or deck.type ~= "Deck" then
        broadcastToAll("The play deck did not come back together.", HOT)
        busy = false
        return
    end

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
            end
            passDealer()
            local name = m and m.getName() or "no mission"
            broadcastToAll("Mission: " .. name .. ".  " .. n ..
                " cards each. Betting starts with the dealer.", GOLD)
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
    broadcastToAll(nxt .. " deals, bets first and leads.", COOL)
end
