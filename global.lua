-- Pili Pili - Tabletop Simulator table script
-- Handles: revealing a mission, dealing the number of cards it prints,
-- hidden betting with the "bets must not total the cards dealt" check,
-- Pili tracking to the 6-Pili end trigger, and table cleanup between rounds.

COLORS = {"Red", "Orange", "Yellow", "Green", "Teal", "Blue", "Purple", "White"}

TAG_PLAY = "PILI:PLAY"
TAG_MISSION = "PILI:MISSION"

POS_PLAY = {-7.0, 1.6, 0.0}
POS_MISSION = {7.0, 1.6, 0.0}
POS_REVEAL = {7.0, 1.6, -5.5}
POS_DISCARD = {11.5, 1.6, 0.0}

GOLD = {0.91, 0.77, 0.36}
HOT = {1.0, 0.38, 0.32}
COOL = {0.55, 0.85, 0.65}

bids = {}
pilis = {}
revealed = false
dealt = 0

-- ------------------------------------------------------------------ state --

function onSave()
    return JSON.encode({bids = bids, pilis = pilis, revealed = revealed, dealt = dealt})
end

function onLoad(state)
    if state ~= nil and state ~= "" then
        local ok, s = pcall(function() return JSON.decode(state) end)
        if ok and s ~= nil then
            bids = s.bids or {}
            pilis = s.pilis or {}
            revealed = s.revealed or false
            dealt = s.dealt or 0
        end
    end
    for _, c in ipairs(COLORS) do
        pilis[c] = pilis[c] or 0
    end
    Wait.time(refreshUI, 1.0)
end

function onPlayerChangeColor(_)
    Wait.time(refreshUI, 0.3)
end

-- ------------------------------------------------------------------ finding --

function findTagged(tag)
    local out = {}
    for _, o in ipairs(getAllObjects()) do
        local t = o.type
        if (t == "Card" or t == "Deck") and o.getGMNotes() == tag then
            table.insert(out, o)
        end
    end
    return out
end

function countCards(o)
    if o.type == "Deck" then
        return #o.getObjects()
    end
    return 1
end

function biggest(tag)
    local best, n = nil, -1
    for _, o in ipairs(findTagged(tag)) do
        local c = countCards(o)
        if c > n then
            best, n = o, c
        end
    end
    return best
end

function missionInPlay()
    local best, bestd = nil, 1e9
    for _, o in ipairs(findTagged(TAG_MISSION)) do
        if o.type == "Card" then
            local p = o.getPosition()
            local d = (p.x - POS_REVEAL[1]) ^ 2 + (p.z - POS_REVEAL[3]) ^ 2
            if d < bestd then
                best, bestd = o, d
            end
        end
    end
    if bestd > 36 then
        return nil
    end
    return best
end

-- ------------------------------------------------------------------ actions --

function uiDrawMission()
    local d = biggest(TAG_MISSION)
    if d == nil then
        broadcastToAll("No mission cards on the table. Press New Game.", HOT)
        return
    end
    local inPlay = missionInPlay()
    if inPlay ~= nil then
        inPlay.setPositionSmooth(POS_DISCARD)
        inPlay.setRotationSmooth({0, 180, 180})
    end
    if d.type == "Deck" then
        d.takeObject({position = POS_REVEAL, rotation = {0, 180, 0}, smooth = true})
    else
        d.setPositionSmooth(POS_REVEAL)
        d.setRotationSmooth({0, 180, 0})
    end
    Wait.time(function()
        local m = missionInPlay()
        if m ~= nil then
            local n = tonumber(string.match(m.getDescription(), "%[deal (%d+)%]")) or 5
            broadcastToAll("Mission: " .. m.getName() .. "  -  deal " .. n .. " cards each.", GOLD)
            status("Mission: " .. m.getName() .. " (" .. n .. " cards)")
        end
    end, 1.3)
end

function uiDeal()
    local seated = getSeatedPlayers()
    if #seated == 0 then
        broadcastToAll("Nobody is seated in a player colour.", HOT)
        return
    end
    local deck = biggest(TAG_PLAY)
    if deck == nil or deck.type ~= "Deck" then
        broadcastToAll("The play deck is not assembled. Press End Round first.", HOT)
        return
    end

    local n = 5
    local m = missionInPlay()
    if m ~= nil then
        n = tonumber(string.match(m.getDescription(), "%[deal (%d+)%]")) or 5
    end

    local avail = countCards(deck)
    local maxn = math.floor(avail / #seated)
    if n > maxn then
        broadcastToAll("Only " .. avail .. " cards for " .. #seated ..
            " players - dealing " .. maxn .. " each instead of " .. n .. ".", HOT)
        n = maxn
    end
    if n < 1 then
        broadcastToAll("Too many players for the cards available.", HOT)
        return
    end

    dealt = n
    bids = {}
    revealed = false
    deck.shuffle()
    Wait.time(function()
        deck.deal(n)
        refreshUI()
    end, 0.7)
    status("Dealt " .. n .. " each. Betting starts with the dealer.")
end

function adjustBid(player, color, delta)
    if player.color ~= color and not player.admin then
        broadcastToColor("That is not your seat.", player.color, HOT)
        return
    end
    local b = (bids[color] or 0) + delta
    if b < 0 then b = 0 end
    if dealt > 0 and b > dealt then b = dealt end
    bids[color] = b
    broadcastToColor("Your bet: " .. b, color, GOLD)
    refreshUI()
end

function bidUp(player, color) adjustBid(player, color, 1) end
function bidDown(player, color) adjustBid(player, color, -1) end

function uiReveal()
    local seated = getSeatedPlayers()
    if #seated == 0 then return end
    revealed = true
    local sum = 0
    local parts = {}
    for _, c in ipairs(seated) do
        local b = bids[c] or 0
        sum = sum + b
        table.insert(parts, c .. " " .. b)
    end
    refreshUI()
    if dealt > 0 and sum == dealt then
        broadcastToAll("Bets total " .. sum .. ", the same as the " .. dealt ..
            " cards dealt. The last bidder must change their bet.", HOT)
        status("ILLEGAL - bets total " .. sum .. " = cards dealt")
    else
        broadcastToAll("Bets: " .. table.concat(parts, "   ") ..
            "   (total " .. sum .. " vs " .. dealt .. " cards)", GOLD)
        status("Bets are in. The dealer leads the first trick.")
    end
end

function gather(tag, pos, thenShuffle)
    local objs = findTagged(tag)
    if #objs == 0 then return end
    local base = table.remove(objs, 1)
    base.setPosition({pos[1], pos[2] + 2.5, pos[3]})
    base.setRotation({0, 180, 180})
    for _, o in ipairs(objs) do
        local r = base.putObject(o)
        if r ~= nil then base = r end
    end
    Wait.time(function()
        if base == nil then return end
        base.setGMNotes(tag)
        if thenShuffle and base.type == "Deck" then base.shuffle() end
        base.setPositionSmooth(pos)
        base.setRotationSmooth({0, 180, 180})
    end, 1.2)
end

function uiEndRound()
    gather(TAG_PLAY, POS_PLAY, true)
    local m = missionInPlay()
    if m ~= nil then
        m.setPositionSmooth(POS_DISCARD)
        m.setRotationSmooth({0, 180, 180})
    end
    bids = {}
    revealed = false
    dealt = 0
    refreshUI()
    status("Round cleared. Award Pilis, then draw a mission.")
end

function uiNewGame()
    gather(TAG_PLAY, POS_PLAY, true)
    gather(TAG_MISSION, POS_MISSION, true)
    bids = {}
    revealed = false
    dealt = 0
    for _, c in ipairs(COLORS) do pilis[c] = 0 end
    refreshUI()
    status("New game. Draw a mission to begin.")
    broadcastToAll("New game - all Pilis cleared.", COOL)
end

-- ------------------------------------------------------------------ pilis --

function setPili(color, v)
    if v < 0 then v = 0 end
    pilis[color] = v
    refreshUI()
    if v >= 6 then
        local bestv = 999
        for _, c in ipairs(getSeatedPlayers()) do
            if (pilis[c] or 0) < bestv then bestv = pilis[c] or 0 end
        end
        local winners = {}
        for _, c in ipairs(getSeatedPlayers()) do
            if (pilis[c] or 0) == bestv then table.insert(winners, c) end
        end
        broadcastToAll(color .. " reached 6 Pilis - the game ends. Fewest Pilis: " ..
            table.concat(winners, " & ") .. " on " .. bestv .. ".", HOT)
        status("GAME OVER - " .. table.concat(winners, " & ") .. " wins on " .. bestv)
    end
end

function piliUp(_, color) setPili(color, (pilis[color] or 0) + 1) end
function piliDown(_, color) setPili(color, (pilis[color] or 0) - 1) end

-- ------------------------------------------------------------------ ui --

function status(txt)
    UI.setValue("status", txt)
end

function refreshUI()
    local seatedSet = {}
    for _, c in ipairs(getSeatedPlayers()) do seatedSet[c] = true end
    for _, c in ipairs(COLORS) do
        UI.setAttribute("row_" .. c, "active", seatedSet[c] and "true" or "false")
        UI.setValue("pili_" .. c, tostring(pilis[c] or 0))
        local b = bids[c]
        local shown = "-"
        if b ~= nil then
            if revealed then shown = tostring(b) else shown = "SET" end
        end
        UI.setValue("bid_" .. c, shown)
    end
    UI.setValue("dealtInfo", dealt > 0 and (dealt .. " cards dealt") or "no hand dealt")
end
