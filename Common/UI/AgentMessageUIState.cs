using Microsoft.Xna.Framework;
using Terraria.GameContent;
using Terraria.GameContent.UI.Elements;
using Terraria.UI.Chat;
using Terraria.UI;

namespace TerrariaFriend.Common.UI
{
	// 伙伴消息框只负责显示智能体回复
	public class AgentMessageUIState : UIState
	{
		private const string DefaultMessage = "UI 已连接。这里将显示 Agent 消息。";
		private const float RightMargin = 20f;
		private const float BottomMargin = 20f;
		private const float PanelWidth = 300f;
		private const float PanelMinHeight = 64f;
		private const float PanelMaxHeight = 240f;
		private const float PanelPadding = 10f;
		private const float MessageTop = 24f;
		private const float MessageTextScale = 0.72f;

		private UIPanel _panel;
		private UIText _messageText;

		public override void OnInitialize()
		{
			_panel = new UIPanel();

			// 固定右下角并让高度变化只向上扩展
			_panel.HAlign = 1f;
			_panel.VAlign = 1f;
			_panel.Left.Set(-RightMargin, 0f);
			_panel.Top.Set(-BottomMargin, 0f);
			_panel.Width.Set(PanelWidth, 0f);
			_panel.Height.Set(PanelMinHeight, 0f);
			_panel.SetPadding(PanelPadding);
			_panel.BackgroundColor = new Color(18, 28, 48, 225);
			_panel.BorderColor = new Color(74, 144, 196, 255);
			_panel.IgnoresMouseInteraction = true;
			_panel.OverflowHidden = true;
			Append(_panel);

			UIText titleText = new UIText("Terraria Friend", 0.78f);
			titleText.TextColor = new Color(116, 210, 255);
			_panel.Append(titleText);

			_messageText = new UIText(DefaultMessage, MessageTextScale);
			_messageText.Top.Set(MessageTop, 0f);
			_messageText.Width.Set(0f, 1f);
			_messageText.Height.Set(-MessageTop, 1f);
			_messageText.IsWrapped = true;
			_messageText.TextColor = Color.White;
			_panel.Append(_messageText);

			UpdatePanelHeight(DefaultMessage);
		}

		public void SetMessage(string message)
		{
			string displayText = string.IsNullOrWhiteSpace(message) ? "（暂无消息）" : message;
			_messageText?.SetText(displayText);
			UpdatePanelHeight(displayText);
			_panel?.Recalculate();
		}

		private void UpdatePanelHeight(string message)
		{
			if (_panel == null)
				return;

			// 使用 UIText 相同的字体换行方式测量实际文本高度
			float textWidth = PanelWidth - PanelPadding * 2f;
			string wrappedText = FontAssets.MouseText.Value.CreateWrappedText(
				message,
				textWidth / MessageTextScale);
			float textHeight = ChatManager.GetStringSize(
				FontAssets.MouseText.Value,
				wrappedText,
				Vector2.One,
				-1f).Y * MessageTextScale;

			float desiredHeight = PanelPadding * 2f + MessageTop + textHeight;
			_panel.Height.Set(MathHelper.Clamp(desiredHeight, PanelMinHeight, PanelMaxHeight), 0f);
		}
	}
}
