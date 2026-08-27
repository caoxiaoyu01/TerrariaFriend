using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace TerrariaFriend.Content.Items
{
	// 基础物品模板
	// 其他示例请参考 tModLoader 的 ExampleMod
	public class SpiriTerra : ModItem
	{
		// 物品显示名称和提示文本可在本地化文件中编辑
		public override void SetDefaults()
		{
			Item.damage = 50;
			Item.DamageType = DamageClass.Melee;
			Item.width = 40;
			Item.height = 40;
			Item.useTime = 20;
			Item.useAnimation = 20;
			Item.useStyle = ItemUseStyleID.Swing;
			Item.knockBack = 6;
			Item.value = Item.buyPrice(silver: 1);
			Item.rare = ItemRarityID.Blue;
			Item.UseSound = SoundID.Item1;
			Item.autoReuse = true;
		}

		// 初始化配方
		public override void AddRecipes()
		{
			Recipe recipe = CreateRecipe();
			recipe.AddIngredient(ItemID.DirtBlock, 10);
			recipe.AddTile(TileID.WorkBenches);
			recipe.Register();
		}
	}
}
