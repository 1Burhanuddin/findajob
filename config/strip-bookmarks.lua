-- strip-bookmarks.lua
-- 1. Clears heading identifiers so pandoc does not emit <w:bookmarkStart> elements
--    in .docx output. Eliminates the blue bookmark icons that appear in Word when
--    "Show bookmarks" is enabled (Word → Options → Advanced → Show document content).
-- 2. Applies "Centered" custom paragraph style to Divs with class "centered".
function Header(el)
  el.identifier = ""
  return el
end

function Div(el)
  if el.classes:includes("centered") then
    -- Apply the Centered custom-style to all paragraphs inside this Div
    local result = pandoc.List()
    for _, block in ipairs(el.content) do
      if block.t == "Para" or block.t == "Plain" then
        result:insert(pandoc.Div({block}, pandoc.Attr("", {}, {{"custom-style", "Centered"}})))
      else
        result:insert(block)
      end
    end
    return result
  end
end
